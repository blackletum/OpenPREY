// Copyright (C) 2004 Id Software, Inc.
//

#include "../../idlib/precompiled.h"
#pragma hdrstop

#include "../Game_local.h"

#include <condition_variable>
#include <deque>
#include <mutex>
#include <thread>

bool idAnimManager::forceExport = false;

idCVar g_useGeneratedAnimCache( "g_useGeneratedAnimCache", "1", CVAR_GAME | CVAR_BOOL | CVAR_ARCHIVE, "load valid generated binary animation caches" );
idCVar g_writeGeneratedAnimCache( "g_writeGeneratedAnimCache", "1", CVAR_GAME | CVAR_BOOL | CVAR_ARCHIVE, "write generated binary animation caches after parsing source animations" );

namespace {

static const unsigned int GENERATED_ANIM_MAGIC = 0x4134514f;	// OQ4A
static const unsigned int GENERATED_ANIM_END_MAGIC = 0x4544514f;	// OQ4E
// Version 3 records the source's logical path (not the host path, so a moved
// install still hits), a CRC of a loose source's bytes, and ends the record
// with a length and CRC-32 trailer. Every count, float and joint reference is
// checked before the animation is published.
static const unsigned int GENERATED_ANIM_VERSION = 3;
static const int MAX_GENERATED_ANIM_FRAMES = 1 << 20;
static const int MAX_GENERATED_ANIM_JOINTS = 4096;
static const int MAX_GENERATED_ANIM_FRAME_RATE = 1000;
static const long long MAX_GENERATED_ANIM_DATA_BYTES = (long long)512 * 1024 * 1024;
static const int MAX_GENERATED_ANIM_RECORD_BYTES = 528 * 1024 * 1024;
static const int GENERATED_ANIM_CRC_TRAILER_BYTES = 2 * sizeof( unsigned int );
static const float GENERATED_ANIM_QUATERNION_EPSILON = 0.01f;

struct generatedAnimSourceInfo_t {
	int			length;
	ID_TIME_T	timestamp;
	int			containerChecksum;
	unsigned int	contentChecksum;	// CRC-32 of a loose source; 0 for a PK4 member
	idStr		normalizedPath;
};

static bool GeneratedAnimSegmentIsWindowsDevice( const char *segment, const int length ) {
	int stemLength = 0;
	while ( stemLength < length && segment[ stemLength ] != '.' ) {
		++stemLength;
	}
	if ( stemLength == 3 ) {
		return ( segment[ 0 ] == 'c' && segment[ 1 ] == 'o' && segment[ 2 ] == 'n' ) ||
			( segment[ 0 ] == 'p' && segment[ 1 ] == 'r' && segment[ 2 ] == 'n' ) ||
			( segment[ 0 ] == 'a' && segment[ 1 ] == 'u' && segment[ 2 ] == 'x' ) ||
			( segment[ 0 ] == 'n' && segment[ 1 ] == 'u' && segment[ 2 ] == 'l' );
	}
	const bool portPrefix = stemLength >= 4 &&
		( ( segment[ 0 ] == 'c' && segment[ 1 ] == 'o' && segment[ 2 ] == 'm' ) ||
		  ( segment[ 0 ] == 'l' && segment[ 1 ] == 'p' && segment[ 2 ] == 't' ) );
	if ( !portPrefix ) {
		return false;
	}

	// COM1-9 and LPT1-9, plus the superscript digits Windows also treats as
	// ports: Latin-1 single bytes, or their two-byte UTF-8 forms (C2 B9/B2/B3)
	const unsigned char digit = static_cast<unsigned char>( segment[ 3 ] );
	if ( stemLength == 4 ) {
		return ( digit >= '1' && digit <= '9' ) || digit == 0xB9 || digit == 0xB2 || digit == 0xB3;
	}

	return stemLength == 5 && digit == 0xC2 &&
		( static_cast<unsigned char>( segment[ 4 ] ) == 0xB9 ||
		  static_cast<unsigned char>( segment[ 4 ] ) == 0xB2 ||
		  static_cast<unsigned char>( segment[ 4 ] ) == 0xB3 );
}

/*
====================
NormalizeGeneratedAnimSourcePath

The cache path is built from the animation's name, so a name that could
escape generated/animations/ or name a device is refused rather than cached.
====================
*/
static bool NormalizeGeneratedAnimSourcePath( const char *filename, idStr &normalized ) {
	if ( filename == NULL || filename[ 0 ] == '\0' ) {
		return false;
	}
	normalized = filename;
	normalized.BackSlashesToSlashes();
	normalized.ToLower();
	if ( normalized.IsEmpty() || normalized[ 0 ] == '/' || normalized.Length() >= MAX_OSPATH ) {
		return false;
	}

	int segmentStart = 0;
	for ( int i = 0; i <= normalized.Length(); ++i ) {
		const unsigned char c = i < normalized.Length() ?
			(unsigned char)normalized[ i ] : (unsigned char)'\0';
		if ( c != '\0' && ( c < 32 || c == 127 || c == ':' || c == '<' || c == '>' ||
				c == '"' || c == '|' || c == '?' || c == '*' ) ) {
			return false;
		}
		if ( c != '/' && c != '\0' ) {
			continue;
		}

		const int segmentLength = i - segmentStart;
		if ( segmentLength == 0 ||
				( segmentLength == 1 && normalized[ segmentStart ] == '.' ) ||
				( segmentLength == 2 && normalized[ segmentStart ] == '.' &&
					normalized[ segmentStart + 1 ] == '.' ) ||
				normalized[ segmentStart ] == ' ' ||
				normalized[ i - 1 ] == '.' || normalized[ i - 1 ] == ' ' ||
				GeneratedAnimSegmentIsWindowsDevice( normalized.c_str() + segmentStart, segmentLength ) ) {
			return false;
		}
		segmentStart = i + 1;
	}
	return true;
}

static bool GetGeneratedAnimPath( const char *filename, idStr &path ) {
	idStr normalized;
	if ( !NormalizeGeneratedAnimSourcePath( filename, normalized ) ) {
		path.Clear();
		return false;
	}
	path = "generated/animations/";
	path += normalized;
	path += ".banim";
	return path.Length() < MAX_OSPATH;
}

/*
====================
GetGeneratedAnimSourceInfo

Identifies the file idMD5Anim::LoadAnim would parse: the compiled companion
when com_binaryRead makes LexerFactory prefer it, else the text source.
====================
*/
static bool GetGeneratedAnimSourceInfo( const char *filename, generatedAnimSourceInfo_t &info ) {
	idStr logicalPath;
	if ( !NormalizeGeneratedAnimSourcePath( filename, logicalPath ) ) {
		return false;
	}

	idStr selectedPath = filename;
	idFile *source = NULL;
	if ( cvarSystem->GetCVarBool( "com_binaryRead" ) ) {
		selectedPath.Append( Lexer::sCompiledFileSuffix );
		source = fileSystem->OpenFileRead( selectedPath, false );
	}
	if ( source == NULL ) {
		selectedPath = filename;
		source = fileSystem->OpenFileRead( selectedPath, false );
	}
	if ( source == NULL ) {
		return false;
	}
	if ( !NormalizeGeneratedAnimSourcePath( selectedPath, info.normalizedPath ) ) {
		fileSystem->CloseFile( source );
		return false;
	}

	info.length = source->Length();
	info.timestamp = source->Timestamp();
	info.containerChecksum = source->GetContainerChecksum();
	info.contentChecksum = 0;

	// A PK4 member is pinned by its pak's checksum. A loose file has only a
	// size and timestamp, which an editor can preserve, so hash its bytes.
	bool valid = info.length >= 0;
	if ( valid && info.containerChecksum == 0 ) {
		uint32_t checksum = 0;
		CRC32_InitChecksum( checksum );
		byte buffer[ 16 * 1024 ];
		int remaining = info.length;
		while ( valid && remaining > 0 ) {
			const int chunkBytes = Min( remaining, (int)sizeof( buffer ) );
			const int readBytes = source->Read( buffer, chunkBytes );
			valid = readBytes == chunkBytes;
			if ( valid ) {
				CRC32_UpdateChecksum( checksum, buffer, readBytes );
				remaining -= readBytes;
			}
		}
		if ( valid ) {
			CRC32_FinishChecksum( checksum );
			info.contentChecksum = checksum;
		}
	}
	fileSystem->CloseFile( source );
	return valid;
}

static bool GeneratedAnimFloatIsFinite( const float value ) {
	// FLOAT_IS_NAN tests the all-ones exponent, so it rejects infinities too
	return !FLOAT_IS_NAN( value );
}

static bool GeneratedAnimFloatsAreFinite( const float *values, const int count ) {
	if ( count < 0 || ( count > 0 && values == NULL ) ) {
		return false;
	}
	for ( int i = 0; i < count; ++i ) {
		if ( !GeneratedAnimFloatIsFinite( values[ i ] ) ) {
			return false;
		}
	}
	return true;
}

static int GeneratedAnimComponentCount( const int animBits ) {
	int bits = animBits & 63;
	int count = 0;
	while ( bits != 0 ) {
		count += bits & 1;
		bits >>= 1;
	}
	return count;
}

static bool CalculateGeneratedAnimLength( const int frameCount, const int frameRate, int &length ) {
	if ( frameCount <= 0 || frameCount > MAX_GENERATED_ANIM_FRAMES ||
			frameRate <= 0 || frameRate > MAX_GENERATED_ANIM_FRAME_RATE ) {
		return false;
	}
	const long long numerator = (long long)( frameCount - 1 ) * 1000 + frameRate - 1;
	const long long result = numerator / frameRate;
	if ( result < 0 || result > 0x7fffffffLL ) {
		return false;
	}
	length = (int)result;
	return true;
}

static unsigned int ReadGeneratedAnimLittleUnsignedInt( const byte *bytes ) {
	unsigned int value = 0;
	memcpy( &value, bytes, sizeof( value ) );
	return (unsigned int)LittleLong( (int)value );
}

static bool ReadGeneratedAnimString( idFile *file, idStr &value, int maxLength ) {
	int length = 0;
	if ( file->ReadInt( length ) != sizeof( length ) || length < 0 || length > maxLength ) {
		return false;
	}
	const int position = file->Tell();
	const int fileLength = file->Length();
	if ( position < 0 || fileLength < position || length > fileLength - position ) {
		return false;
	}

	if ( length == 0 ) {
		value.Clear();
		return true;
	}

	value.Fill( ' ', length );
	if ( file->Read( &value[ 0 ], length ) != length ) {
		value.Clear();
		return false;
	}
	for ( int i = 0; i < length; ++i ) {
		if ( value[ i ] == '\0' ) {
			value.Clear();
			return false;
		}
	}
	return true;
}

static bool ReadGeneratedAnimFloats( idFile *file, float *values, int count ) {
	if ( count < 0 || ( count > 0 && values == NULL ) ) {
		return false;
	}
	const long long byteCount = (long long)count * sizeof( float );
	const int position = file->Tell();
	const int fileLength = file->Length();
	if ( position < 0 || fileLength < position ||
			byteCount > fileLength - position || byteCount > 0x7fffffff ) {
		return false;
	}
	if ( count > 0 && file->Read( values, (int)byteCount ) != byteCount ) {
		return false;
	}
	LittleRevBytes( values, sizeof( float ), count );
	return GeneratedAnimFloatsAreFinite( values, count );
}

static void SplitGeneratedAnimTimestamp( ID_TIME_T timestamp, unsigned int &low, unsigned int &high ) {
	const unsigned long long value = (unsigned long long)timestamp;
	low = (unsigned int)( value & 0xffffffffu );
	high = (unsigned int)( value >> 32 );
}

/*
====================
generatedAnimBuffer_t

Builds a generated animation cache in memory, byte for byte what idFile's
WriteInt, WriteUnsignedInt and WriteVec3 put on disk.
====================
*/
struct generatedAnimBuffer_t {
	idList< byte >	bytes;


	void Raw( const void *data, int length ) {
		if ( length <= 0 ) {
			return;
		}
		const int start = bytes.Num();
		if ( start + length > bytes.NumAllocated() ) {
			bytes.Resize( Max( start + length, bytes.NumAllocated() * 2 ) );
		}
		bytes.SetNum( start + length, false );
		memcpy( bytes.Ptr() + start, data, length );
	}
	void Int( int value ) { const int v = LittleLong( value ); Raw( &v, sizeof( v ) ); }
	void UnsignedInt( unsigned int value ) { const unsigned int v = LittleLong( value ); Raw( &v, sizeof( v ) ); }
	void Vec3( const idVec3 &value ) {
		idVec3 v = value;
		LittleRevBytes( &v, sizeof( float ), sizeof( v ) / sizeof( float ) );
		Raw( &v, sizeof( v ) );
	}
	bool String( const char *value ) {
		if ( value == NULL ) {
			value = "";
		}
		const size_t valueLength = strlen( value );
		if ( valueLength > MAX_STRING_CHARS ) {
			return false;
		}
		Int( (int)valueLength );
		Raw( value, (int)valueLength );
		return true;
	}
	bool Floats( const float *values, int count ) {
		if ( count < 0 || ( count > 0 && values == NULL ) ) {
			return false;
		}
		const long long byteCount = (long long)count * sizeof( float );
		if ( byteCount > 0x7fffffff || (long long)bytes.Num() + byteCount > 0x7fffffff ) {
			return false;
		}
		if ( !GeneratedAnimFloatsAreFinite( values, count ) ) {
			return false;
		}
		const int start = bytes.Num();
		Raw( values, (int)byteCount );
		if ( !Swap_IsBigEndian() ) {
			return true;
		}
		LittleRevBytes( bytes.Ptr() + start, sizeof( float ), count );
		return true;
	}
};

/*
====================
idGeneratedAnimWriter

The first visit to a map parses its source animations and writes a binary
cache for each, hundreds of small files. Creating, writing and closing them
on the load thread was most of a first visit's extra time. The load thread
now opens each cache's staging file (<cache>.tmp) through the filesystem
and builds its bytes in memory; this writer writes, syncs and closes the
staging files on its own thread while the load goes on. The final name only
ever holds a complete record: a written staging file is promoted over it
with the filesystem's atomic replace, on the main thread, because promotion
clears the filesystem's directory cache, which the main thread reads. The
main thread promotes whatever is ready each time it queues or reads a
cache, and at shutdown, which first waits for every queued file. A cache
not yet promoted is just a miss, and the CRC trailer rejects any record
that is not the one written.
====================
*/
class idGeneratedAnimWriter {
public:
	~idGeneratedAnimWriter() { Shutdown(); }

	// Opens stagedPath on this (the load) thread once the queue has room, and
	// hands the open file and data to the writer thread, which writes, syncs
	// and closes it. Every queued file stays open until then, and the C
	// runtime allows only so many open streams for the whole process: the
	// queue holds at most MAX_OPEN_FILES, or the filesystem could fail to
	// open a pk4.
	void Queue( const char *stagedPath, const char *cachePath, idList< byte > &data ) {
		PromoteWritten();
		const size_t size = static_cast<size_t>( data.Num() );
		{
			std::unique_lock<std::mutex> lock( mutex );
			if ( !thread.joinable() ) {
				stopping = false;
				thread = std::thread( &idGeneratedAnimWriter::Run, this );
			}
			room.wait( lock, [&] {
				return openFiles < MAX_OPEN_FILES && ( pendingBytes == 0 || pendingBytes + size <= MAX_PENDING_BYTES );
			} );
			++openFiles;
			pendingBytes += size;
		}
		idFile *stagedCache = fileSystem->OpenFileWrite( stagedPath, "fs_savepath" );
		std::lock_guard<std::mutex> lock( mutex );
		if ( stagedCache == NULL ) {
			--openFiles;
			pendingBytes -= size;
			return;
		}
		jobs.emplace_back();
		jobs.back().stagedCache = stagedCache;
		jobs.back().stagedPath = stagedPath;
		jobs.back().cachePath = cachePath;
		jobs.back().data.Swap( data );
		ready.notify_one();
	}

	// Main thread only: moves every fully written staging file to its final
	// name, and removes any that failed to write.
	void PromoteWritten() {
		std::deque< written_t > batch;
		{
			std::lock_guard<std::mutex> lock( mutex );
			if ( written.empty() ) {
				return;
			}
			batch.swap( written );
		}
		for ( written_t &entry : batch ) {
			const idStr &stagedPath = entry.stagedPath;
			const idStr &cachePath = entry.cachePath;
			if ( !entry.valid || !fileSystem->PromoteFile( stagedPath, cachePath, "fs_savepath" ) ) {
				fileSystem->RemoveFileChecked( stagedPath, "fs_savepath" );
			}
		}
	}

	void Shutdown() {
		bool joined = false;
		{
			std::lock_guard<std::mutex> lock( mutex );
			if ( thread.joinable() ) {
				stopping = true;
				joined = true;
			}
		}
		if ( joined ) {
			ready.notify_one();
			thread.join();
		}
		PromoteWritten();
	}

private:
	struct job_t {
		idFile *		stagedCache = NULL;
		idStr			stagedPath;
		idStr			cachePath;
		idList< byte >	data;
	};
	struct written_t {
		idStr			stagedPath;
		idStr			cachePath;
		bool			valid = false;
	};

	static constexpr int MAX_OPEN_FILES = 16;
	static constexpr size_t MAX_PENDING_BYTES = 64u << 20;

	void Run() {
		for ( ;; ) {
			job_t job;
			{
				std::unique_lock<std::mutex> lock( mutex );
				ready.wait( lock, [&] { return stopping || !jobs.empty(); } );
				if ( jobs.empty() ) {
					return;
				}
				job.stagedCache = jobs.front().stagedCache;
				job.stagedPath = jobs.front().stagedPath;
				job.cachePath = jobs.front().cachePath;
				job.data.Swap( jobs.front().data );
				jobs.pop_front();
			}
			const int size = job.data.Num();
			// The file and its stdio stream belong to this job alone.
			idFile *stagedCache = job.stagedCache;
			bool valid = size > 0 && stagedCache->Write( job.data.Ptr(), size ) == size;
			valid = valid && stagedCache->Sync();
			if ( !valid ) {
				common->Printf( "generated animation cache '%s' was not fully written\n", job.cachePath.c_str() );
			}
			fileSystem->CloseFile( stagedCache );
			{
				std::lock_guard<std::mutex> lock( mutex );
				--openFiles;
				pendingBytes -= static_cast<size_t>( size );
				written.emplace_back();
				written.back().stagedPath = job.stagedPath;
				written.back().cachePath = job.cachePath;
				written.back().valid = valid;
			}
			room.notify_all();
		}
	}

	std::mutex				mutex;
	std::condition_variable	ready;
	std::condition_variable	room;
	std::deque< job_t >		jobs;
	std::deque< written_t >	written;	// staged and closed, awaiting promotion
	std::thread				thread;
	size_t					pendingBytes = 0;
	int						openFiles = 0;		// queued or being written
	bool					stopping = false;
};

static idGeneratedAnimWriter generatedAnimWriter;

static ID_TIME_T JoinGeneratedAnimTimestamp( unsigned int low, unsigned int high ) {
	return (ID_TIME_T)( ( (unsigned long long)high << 32 ) | low );
}

}

/***********************************************************************

	idMD5Anim

***********************************************************************/

/*
====================
idMD5Anim::idMD5Anim
====================
*/
idMD5Anim::idMD5Anim() {
	ref_count	= 0;
	fromGeneratedCache = false;
	numFrames	= 0;
	numJoints	= 0;
	frameRate	= 24;
	animLength	= 0;
	totaldelta.Zero();
}

/*
====================
idMD5Anim::idMD5Anim
====================
*/
idMD5Anim::~idMD5Anim() {
	Free();
}

/*
====================
idMD5Anim::Free
====================
*/
void idMD5Anim::Free( void ) {
	numFrames	= 0;
	numJoints	= 0;
	frameRate	= 24;
	animLength	= 0;
	name		= "";
	fromGeneratedCache = false;

	totaldelta.Zero();

	jointInfo.Clear();
	bounds.Clear();
	baseFrame.Clear();
	componentFrames.Clear();
}

/*
====================
idMD5Anim::NumFrames
====================
*/
int	idMD5Anim::NumFrames( void ) const {
	return numFrames;
}

/*
====================
idMD5Anim::NumJoints
====================
*/
int	idMD5Anim::NumJoints( void ) const {
	return numJoints;
}

/*
====================
idMD5Anim::Length
====================
*/
int idMD5Anim::Length( void ) const {
	return animLength;
}

/*
=====================
idMD5Anim::TotalMovementDelta
=====================
*/
const idVec3 &idMD5Anim::TotalMovementDelta( void ) const {
	return totaldelta;
}

/*
=====================
idMD5Anim::TotalMovementDelta
=====================
*/
const char *idMD5Anim::Name( void ) const {
	return name;
}

/*
====================
idMD5Anim::Reload
====================
*/
bool idMD5Anim::Reload( void ) {
	idStr filename;

	filename = name;
	Free();

	return LoadAnim( filename );
}

/*
====================
idMD5Anim::Allocated
====================
*/
size_t idMD5Anim::Allocated( void ) const {
	size_t	size = bounds.Allocated() + jointInfo.Allocated() + baseFrame.Allocated() + componentFrames.Allocated() + name.Allocated();
	return size;
}

/*
====================
idMD5Anim::LoadGeneratedAnim

Reads generated/animations/<source>.banim from fs_savepath only. The record
is CRC-checked whole before a field of it is parsed, and every count, float
and joint reference is validated into private lists; the animation is
published only once the whole record is valid. A stale cache (the source
changed) is a plain miss; a damaged one is removed so it is rebuilt.
====================
*/
bool idMD5Anim::LoadGeneratedAnim( const char *filename ) {
	// No generated cache is read while a pure lock or fs_restrict holds. An
	// animation decoded before then is re-derived at the next map load; see
	// idAnimManager::ReloadGeneratedCacheAnims.
	if ( !fileSystem->GeneratedCacheReadsEnabled( GENERATED_CACHE_ANIMATION ) ) {
		return false;
	}
	generatedAnimWriter.PromoteWritten();

	idStr cachePath;
	if ( !GetGeneratedAnimPath( filename, cachePath ) ) {
		return false;
	}

	// The cache is private derived data: never resolve it through the search
	// paths, where a pak or another game directory could supply one.
	idStr cacheOSPath = fileSystem->RelativePathToOSPath( cachePath, "fs_savepath" );
	idFile *diskCache = fileSystem->OpenExplicitFileRead( cacheOSPath );
	if ( diskCache == NULL ) {
		return false;
	}

	const int diskLength = diskCache->Length();
	bool valid = diskLength > GENERATED_ANIM_CRC_TRAILER_BYTES &&
		diskLength <= MAX_GENERATED_ANIM_RECORD_BYTES + GENERATED_ANIM_CRC_TRAILER_BYTES;
	idList< byte > diskBytes;
	if ( valid ) {
		diskBytes.SetGranularity( 1 );
		diskBytes.SetNum( diskLength );
		valid = diskCache->Read( diskBytes.Ptr(), diskLength ) == diskLength &&
			diskCache->Tell() == diskLength;
	}
	fileSystem->CloseFile( diskCache );

	// trailer: record length, then CRC-32 of the record, both little-endian
	const int recordLength = valid ? diskLength - GENERATED_ANIM_CRC_TRAILER_BYTES : 0;
	if ( valid ) {
		const unsigned int storedLength = ReadGeneratedAnimLittleUnsignedInt( diskBytes.Ptr() + recordLength );
		const unsigned int storedChecksum = ReadGeneratedAnimLittleUnsignedInt(
			diskBytes.Ptr() + recordLength + sizeof( unsigned int ) );
		valid = storedLength == (unsigned int)recordLength &&
			storedChecksum == CRC32_BlockChecksum( diskBytes.Ptr(), recordLength );
	}

	idFile *cache = NULL;
	if ( valid ) {
		cache = fileSystem->GetNewFileMemory();
		valid = cache != NULL &&
			cache->Write( diskBytes.Ptr(), recordLength ) == recordLength;
		if ( valid ) {
			cache->MakeReadOnly();
			valid = cache->Length() == recordLength && cache->Tell() == 0;
		}
	}
	diskBytes.Clear();
	if ( !valid ) {
		if ( cache != NULL ) {
			fileSystem->CloseFile( cache );
		}
		fileSystem->RemoveFileChecked( cachePath, "fs_savepath" );
		return false;
	}

	generatedAnimSourceInfo_t sourceInfo;
	if ( !GetGeneratedAnimSourceInfo( filename, sourceInfo ) ) {
		fileSystem->CloseFile( cache );
		return false;
	}

	unsigned int magic = 0;
	unsigned int version = 0;
	int sourceLength = -1;
	int sourceContainerChecksum = 0;
	unsigned int sourceContentChecksum = 0;
	unsigned int timestampLow = 0;
	unsigned int timestampHigh = 0;
	idStr sourcePath;
	int cachedNumFrames = 0;
	int cachedNumJoints = 0;
	int cachedFrameRate = 0;
	int cachedNumAnimatedComponents = 0;
	idVec3 cachedTotalDelta;

	valid =
		cache->ReadUnsignedInt( magic ) == sizeof( magic ) &&
		cache->ReadUnsignedInt( version ) == sizeof( version ) &&
		cache->ReadInt( sourceLength ) == sizeof( sourceLength ) &&
		cache->ReadInt( sourceContainerChecksum ) == sizeof( sourceContainerChecksum ) &&
		cache->ReadUnsignedInt( sourceContentChecksum ) == sizeof( sourceContentChecksum ) &&
		cache->ReadUnsignedInt( timestampLow ) == sizeof( timestampLow ) &&
		cache->ReadUnsignedInt( timestampHigh ) == sizeof( timestampHigh ) &&
		ReadGeneratedAnimString( cache, sourcePath, MAX_STRING_CHARS ) &&
		cache->ReadInt( cachedNumFrames ) == sizeof( cachedNumFrames ) &&
		cache->ReadInt( cachedNumJoints ) == sizeof( cachedNumJoints ) &&
		cache->ReadInt( cachedFrameRate ) == sizeof( cachedFrameRate ) &&
		cache->ReadInt( cachedNumAnimatedComponents ) == sizeof( cachedNumAnimatedComponents ) &&
		cache->ReadVec3( cachedTotalDelta ) == sizeof( cachedTotalDelta );

	const ID_TIME_T sourceTimestamp = JoinGeneratedAnimTimestamp( timestampLow, timestampHigh );
	valid = valid &&
		magic == GENERATED_ANIM_MAGIC &&
		version == GENERATED_ANIM_VERSION &&
		sourceLength == sourceInfo.length &&
		sourceContainerChecksum == sourceInfo.containerChecksum &&
		sourceContentChecksum == sourceInfo.contentChecksum &&
		sourceTimestamp == sourceInfo.timestamp &&
		sourcePath.Cmp( sourceInfo.normalizedPath ) == 0 &&
		cachedNumFrames > 0 && cachedNumFrames <= MAX_GENERATED_ANIM_FRAMES &&
		cachedNumJoints > 0 && cachedNumJoints <= MAX_GENERATED_ANIM_JOINTS &&
		cachedFrameRate > 0 && cachedFrameRate <= MAX_GENERATED_ANIM_FRAME_RATE &&
		cachedNumAnimatedComponents >= 0 &&
		cachedNumAnimatedComponents <= cachedNumJoints * 6 &&
		GeneratedAnimFloatsAreFinite( cachedTotalDelta.ToFloatPtr(), 3 );

	long long componentCount = 0;
	if ( valid ) {
		componentCount = (long long)cachedNumFrames * cachedNumAnimatedComponents;
		const long long dataBytes =
			(long long)cachedNumFrames * 6 * sizeof( float ) +
			(long long)cachedNumJoints * 7 * sizeof( float ) +
			componentCount * sizeof( float );
		valid = componentCount <= 0x7fffffff &&
			dataBytes >= 0 && dataBytes <= MAX_GENERATED_ANIM_DATA_BYTES;
	}

	int cachedAnimLength = 0;
	valid = valid && CalculateGeneratedAnimLength( cachedNumFrames, cachedFrameRate, cachedAnimLength );

	idStrList cachedJointNames;
	idList< jointAnimInfo_t > cachedJointInfo;
	idList< idBounds > cachedBounds;
	idList< idJointQuat > cachedBaseFrame;
	idList< float > cachedComponentFrames;

	if ( valid ) {
		cachedJointNames.SetNum( cachedNumJoints );
		cachedJointInfo.SetGranularity( 1 );
		cachedJointInfo.SetNum( cachedNumJoints );
		for ( int i = 0; valid && i < cachedNumJoints; ++i ) {
			jointAnimInfo_t &joint = cachedJointInfo[ i ];
			joint.parentNum = -2;
			joint.animBits = 0;
			joint.firstComponent = -1;
			valid =
				ReadGeneratedAnimString( cache, cachedJointNames[ i ], MAX_STRING_CHARS ) &&
				cache->ReadInt( joint.parentNum ) == sizeof( joint.parentNum ) &&
				cache->ReadInt( joint.animBits ) == sizeof( joint.animBits ) &&
				cache->ReadInt( joint.firstComponent ) == sizeof( joint.firstComponent );
			joint.nameIndex = 0;
			// a joint's components must lie inside each frame's component run
			const int jointComponentCount = GeneratedAnimComponentCount( joint.animBits );
			valid = valid &&
				( ( i == 0 && joint.parentNum == -1 ) ||
					( i > 0 && joint.parentNum >= 0 && joint.parentNum < i ) ) &&
				( joint.animBits & ~63 ) == 0 &&
				joint.firstComponent >= 0 &&
				joint.firstComponent <= cachedNumAnimatedComponents &&
				jointComponentCount <= cachedNumAnimatedComponents - joint.firstComponent;
		}
	}

	if ( valid ) {
		cachedBounds.SetGranularity( 1 );
		cachedBounds.SetNum( cachedNumFrames );
		valid = ReadGeneratedAnimFloats( cache, cachedBounds[ 0 ][ 0 ].ToFloatPtr(), cachedNumFrames * 6 );
		for ( int i = 0; valid && i < cachedNumFrames; ++i ) {
			for ( int axis = 0; axis < 3; ++axis ) {
				valid = cachedBounds[ i ][ 0 ][ axis ] <= cachedBounds[ i ][ 1 ][ axis ];
				if ( !valid ) {
					break;
				}
			}
		}
	}

	idList< float > cachedBaseFrameData;
	if ( valid ) {
		cachedBaseFrameData.SetGranularity( 1 );
		cachedBaseFrameData.SetNum( cachedNumJoints * 7 );
		valid = ReadGeneratedAnimFloats( cache, cachedBaseFrameData.Ptr(), cachedBaseFrameData.Num() );
	}

	if ( valid ) {
		cachedBaseFrame.SetGranularity( 1 );
		cachedBaseFrame.SetNum( cachedNumJoints );
		for ( int i = 0; valid && i < cachedNumJoints; ++i ) {
			const float *source = cachedBaseFrameData.Ptr() + i * 7;
			memset( &cachedBaseFrame[ i ], 0, sizeof( cachedBaseFrame[ i ] ) );
			cachedBaseFrame[ i ].q.Set( source[ 0 ], source[ 1 ], source[ 2 ], source[ 3 ] );
			cachedBaseFrame[ i ].t.Set( source[ 4 ], source[ 5 ], source[ 6 ] );
			const float quaternionLengthSqr = source[ 0 ] * source[ 0 ] +
				source[ 1 ] * source[ 1 ] + source[ 2 ] * source[ 2 ] + source[ 3 ] * source[ 3 ];
			valid = GeneratedAnimFloatIsFinite( quaternionLengthSqr ) &&
				idMath::Fabs( quaternionLengthSqr - 1.0f ) <= GENERATED_ANIM_QUATERNION_EPSILON;
		}

		if ( valid ) {
			cachedComponentFrames.SetGranularity( 1 );
			cachedComponentFrames.SetNum( (int)componentCount );
			valid = ReadGeneratedAnimFloats( cache, cachedComponentFrames.Ptr(), cachedComponentFrames.Num() );
		}
	}

	unsigned int endMagic = 0;
	if ( valid ) {
		valid = cache->ReadUnsignedInt( endMagic ) == sizeof( endMagic ) &&
			endMagic == GENERATED_ANIM_END_MAGIC &&
			cache->Tell() == cache->Length();
	}
	fileSystem->CloseFile( cache );

	if ( !valid ) {
		fileSystem->RemoveFileChecked( cachePath, "fs_savepath" );
		return false;
	}

	for ( int i = 0; i < cachedNumJoints; ++i ) {
		cachedJointInfo[ i ].nameIndex = animationLib.JointIndex( cachedJointNames[ i ] );
	}

	Free();
	name = filename;
	fromGeneratedCache = true;
	numFrames = cachedNumFrames;
	numJoints = cachedNumJoints;
	frameRate = cachedFrameRate;
	numAnimatedComponents = cachedNumAnimatedComponents;
	totaldelta = cachedTotalDelta;
	animLength = cachedAnimLength;
	jointInfo.Swap( cachedJointInfo );
	bounds.Swap( cachedBounds );
	baseFrame.Swap( cachedBaseFrame );
	componentFrames.Swap( cachedComponentFrames );
	return true;
}

/*
====================
idMD5Anim::WriteGeneratedAnim

Validates the parsed animation the way LoadGeneratedAnim validates a cache,
so nothing is written that would be rejected on reading, then queues the
record and its length/CRC-32 trailer for a staged, atomically promoted write.
====================
*/
void idMD5Anim::WriteGeneratedAnim( const char *filename ) const {
	generatedAnimSourceInfo_t sourceInfo;
	if ( !GetGeneratedAnimSourceInfo( filename, sourceInfo ) ) {
		return;
	}

	idStr cachePath;
	if ( !GetGeneratedAnimPath( filename, cachePath ) ) {
		return;
	}

	unsigned int timestampLow = 0;
	unsigned int timestampHigh = 0;
	SplitGeneratedAnimTimestamp( sourceInfo.timestamp, timestampLow, timestampHigh );

	int calculatedAnimLength = 0;
	bool valid = CalculateGeneratedAnimLength( numFrames, frameRate, calculatedAnimLength ) &&
		calculatedAnimLength == animLength &&
		numJoints > 0 && numJoints <= MAX_GENERATED_ANIM_JOINTS &&
		numAnimatedComponents >= 0 && numAnimatedComponents <= numJoints * 6 &&
		jointInfo.Num() == numJoints && bounds.Num() == numFrames &&
		baseFrame.Num() == numJoints &&
		GeneratedAnimFloatsAreFinite( totaldelta.ToFloatPtr(), 3 );
	long long componentCount = 0;
	if ( valid ) {
		componentCount = (long long)numFrames * numAnimatedComponents;
		const long long dataBytes =
			(long long)numFrames * 6 * sizeof( float ) +
			(long long)numJoints * 7 * sizeof( float ) +
			componentCount * sizeof( float );
		valid = componentCount <= 0x7fffffff &&
			componentFrames.Num() == (int)componentCount &&
			dataBytes >= 0 && dataBytes <= MAX_GENERATED_ANIM_DATA_BYTES;
	}
	for ( int i = 0; valid && i < numFrames; ++i ) {
		for ( int axis = 0; axis < 3; ++axis ) {
			valid = GeneratedAnimFloatIsFinite( bounds[ i ][ 0 ][ axis ] ) &&
				GeneratedAnimFloatIsFinite( bounds[ i ][ 1 ][ axis ] ) &&
				bounds[ i ][ 0 ][ axis ] <= bounds[ i ][ 1 ][ axis ];
			if ( !valid ) {
				break;
			}
		}
	}
	if ( !valid ) {
		return;
	}

	generatedAnimBuffer_t cache;
	cache.UnsignedInt( GENERATED_ANIM_MAGIC );
	cache.UnsignedInt( GENERATED_ANIM_VERSION );
	cache.Int( sourceInfo.length );
	cache.Int( sourceInfo.containerChecksum );
	cache.UnsignedInt( sourceInfo.contentChecksum );
	cache.UnsignedInt( timestampLow );
	cache.UnsignedInt( timestampHigh );
	valid = cache.String( sourceInfo.normalizedPath );
	cache.Int( numFrames );
	cache.Int( numJoints );
	cache.Int( frameRate );
	cache.Int( numAnimatedComponents );
	cache.Vec3( totaldelta );

	for ( int i = 0; valid && i < numJoints; ++i ) {
		const jointAnimInfo_t &joint = jointInfo[ i ];
		const int jointComponentCount = GeneratedAnimComponentCount( joint.animBits );
		valid =
			( ( i == 0 && joint.parentNum == -1 ) ||
				( i > 0 && joint.parentNum >= 0 && joint.parentNum < i ) ) &&
			( joint.animBits & ~63 ) == 0 &&
			joint.firstComponent >= 0 &&
			joint.firstComponent <= numAnimatedComponents &&
			jointComponentCount <= numAnimatedComponents - joint.firstComponent &&
			cache.String( animationLib.JointName( joint.nameIndex ) );
		cache.Int( joint.parentNum );
		cache.Int( joint.animBits );
		cache.Int( joint.firstComponent );
	}

	if ( valid ) {
		valid = cache.Floats( bounds[ 0 ][ 0 ].ToFloatPtr(), numFrames * 6 );
	}

	if ( valid ) {
		idList< float > baseFrameData;
		baseFrameData.SetGranularity( 1 );
		baseFrameData.SetNum( numJoints * 7 );
		for ( int i = 0; valid && i < numJoints; ++i ) {
			float *destination = baseFrameData.Ptr() + i * 7;
			destination[ 0 ] = baseFrame[ i ].q.x;
			destination[ 1 ] = baseFrame[ i ].q.y;
			destination[ 2 ] = baseFrame[ i ].q.z;
			destination[ 3 ] = baseFrame[ i ].q.w;
			destination[ 4 ] = baseFrame[ i ].t.x;
			destination[ 5 ] = baseFrame[ i ].t.y;
			destination[ 6 ] = baseFrame[ i ].t.z;
			const float quaternionLengthSqr = destination[ 0 ] * destination[ 0 ] +
				destination[ 1 ] * destination[ 1 ] + destination[ 2 ] * destination[ 2 ] +
				destination[ 3 ] * destination[ 3 ];
			valid = GeneratedAnimFloatIsFinite( quaternionLengthSqr ) &&
				idMath::Fabs( quaternionLengthSqr - 1.0f ) <= GENERATED_ANIM_QUATERNION_EPSILON;
		}
		valid = valid && cache.Floats( baseFrameData.Ptr(), baseFrameData.Num() );
	}

	if ( valid ) {
		valid = cache.Floats( componentFrames.Ptr(), componentFrames.Num() );
	}
	if ( !valid ) {
		return;
	}
	cache.UnsignedInt( GENERATED_ANIM_END_MAGIC );

	const int recordLength = cache.bytes.Num();
	if ( recordLength <= 0 || recordLength > MAX_GENERATED_ANIM_RECORD_BYTES ) {
		return;
	}
	const unsigned int recordChecksum = CRC32_BlockChecksum( cache.bytes.Ptr(), recordLength );
	cache.UnsignedInt( (unsigned int)recordLength );
	cache.UnsignedInt( recordChecksum );

	idStr stagedPath = cachePath;
	stagedPath += ".tmp";
	generatedAnimWriter.Queue( stagedPath, cachePath, cache.bytes );
}

/*
====================
idMD5Anim_FinishGeneratedCacheWrites

Waits until every queued generated animation cache is on disk under its
final name.
====================
*/
void idMD5Anim_FinishGeneratedCacheWrites( void ) {
	generatedAnimWriter.Shutdown();
}

/*
====================
idMD5Anim::LoadAnim
====================
*/
bool idMD5Anim::LoadAnim( const char *filename ) {
	fileSystem->RecordLevelLoadResource( LEVEL_LOAD_RESOURCE_ANIMATION,
		filename, "md5anim", 0, 2 );
	if ( g_useGeneratedAnimCache.GetBool() && LoadGeneratedAnim( filename ) ) {
		return true;
	}

	int		version;
	// openPR06: LexerFactory reads the compiled companion only under
	// com_binaryRead (else it is idLexer, as before), which is the file
	// GetGeneratedAnimSourceInfo names as this animation's source.
	idAutoPtr<Lexer>	lexer( LexerFactory::MakeLexer( LEXFL_ALLOWPATHNAMES | LEXFL_NOSTRINGESCAPECHARS | LEXFL_NOSTRINGCONCAT ) );
	Lexer	&parser( *lexer );
	idToken	token;
	int		i, j;
	int		num;

	if ( !parser.LoadFile( filename ) ) {
		return false;
	}

	Free();

	name = filename;

	parser.ExpectTokenString( MD5_VERSION_STRING );
	version = parser.ParseInt();
	if ( version != MD5_VERSION ) {
		parser.Error( "Invalid version %d.  Should be version %d\n", version, MD5_VERSION );
	}

	// skip the commandline
	parser.ExpectTokenString( "commandline" );
	parser.ReadToken( &token );

	// parse num frames
	parser.ExpectTokenString( "numFrames" );
	numFrames = parser.ParseInt();
	if ( numFrames <= 0 ) {
		parser.Error( "Invalid number of frames: %d", numFrames );
	}

	// parse num joints
	parser.ExpectTokenString( "numJoints" );
	numJoints = parser.ParseInt();
	if ( numJoints <= 0 ) {
		parser.Error( "Invalid number of joints: %d", numJoints );
	}

	// parse frame rate
	parser.ExpectTokenString( "frameRate" );
	frameRate = parser.ParseInt();
	// openPR06: a rate of 0 divided by zero in the length below; every retail
	// animation runs at 12-96 fps
	if ( frameRate <= 0 || frameRate > MAX_GENERATED_ANIM_FRAME_RATE ) {
		parser.Error( "Invalid frame rate: %d", frameRate );
	}

	// parse number of animated components
	parser.ExpectTokenString( "numAnimatedComponents" );
	numAnimatedComponents = parser.ParseInt();
	if ( ( numAnimatedComponents < 0 ) || ( numAnimatedComponents > numJoints * 6 ) ) {
		parser.Error( "Invalid number of animated components: %d", numAnimatedComponents );
	}
	// openPR06: the frame table below holds numAnimatedComponents * numFrames
	// floats, a product taken in int that could wrap and let the frame loop
	// write past the table. The generated-anim reader holds to the same limits.
	if ( numFrames > MAX_GENERATED_ANIM_FRAMES || numJoints > MAX_GENERATED_ANIM_JOINTS ||
			static_cast<long long>( numAnimatedComponents ) * numFrames > 0x7fffffff / static_cast<int>( sizeof( float ) ) ) {
		parser.Error( "Animation is too large: %d frames, %d joints, %d components", numFrames, numJoints, numAnimatedComponents );
	}

	// parse the hierarchy
	jointInfo.SetGranularity( 1 );
	jointInfo.SetNum( numJoints );
	parser.ExpectTokenString( "hierarchy" );
	parser.ExpectTokenString( "{" );
	for( i = 0; i < numJoints; i++ ) {
		parser.ReadToken( &token );
		jointInfo[ i ].nameIndex = animationLib.JointIndex( token );
		
		// parse parent num
		jointInfo[ i ].parentNum = parser.ParseInt();
		if ( jointInfo[ i ].parentNum >= i ) {
			parser.Error( "Invalid parent num: %d", jointInfo[ i ].parentNum );
		}

		if ( ( i != 0 ) && ( jointInfo[ i ].parentNum < 0 ) ) {
			parser.Error( "Animations may have only one root joint" );
		}

		// parse anim bits
		jointInfo[ i ].animBits = parser.ParseInt();
		if ( jointInfo[ i ].animBits & ~63 ) {
			parser.Error( "Invalid anim bits: %d", jointInfo[ i ].animBits );
		}

		// parse first component
		jointInfo[ i ].firstComponent = parser.ParseInt();
		// openPR06: the joint's components, not just the first, must lie in
		// the frame's component run (all retail animations do)
		const int jointComponentCount = GeneratedAnimComponentCount( jointInfo[ i ].animBits );
		if ( jointInfo[ i ].firstComponent < 0 ||
				jointInfo[ i ].firstComponent > numAnimatedComponents ||
				jointComponentCount > numAnimatedComponents - jointInfo[ i ].firstComponent ) {
			parser.Error( "Invalid first component: %d", jointInfo[ i ].firstComponent );
		}
	}

	parser.ExpectTokenString( "}" );

	// parse bounds
	parser.ExpectTokenString( "bounds" );
	parser.ExpectTokenString( "{" );
	bounds.SetGranularity( 1 );
	bounds.SetNum( numFrames );
	for( i = 0; i < numFrames; i++ ) {
		parser.Parse1DMatrix( 3, bounds[ i ][ 0 ].ToFloatPtr() );
		parser.Parse1DMatrix( 3, bounds[ i ][ 1 ].ToFloatPtr() );
	}
	parser.ExpectTokenString( "}" );

	// parse base frame
	baseFrame.SetGranularity( 1 );
	baseFrame.SetNum( numJoints );
	parser.ExpectTokenString( "baseframe" );
	parser.ExpectTokenString( "{" );
	for( i = 0; i < numJoints; i++ ) {
		idCQuat q;
		parser.Parse1DMatrix( 3, baseFrame[ i ].t.ToFloatPtr() );
		parser.Parse1DMatrix( 3, q.ToFloatPtr() );//baseFrame[ i ].q.ToFloatPtr() );
		baseFrame[ i ].q = q.ToQuat();//.w = baseFrame[ i ].q.CalcW();
	}
	parser.ExpectTokenString( "}" );

	// parse frames
	componentFrames.SetGranularity( 1 );
	componentFrames.SetNum( numAnimatedComponents * numFrames );

	float *componentPtr = componentFrames.Ptr();
	for( i = 0; i < numFrames; i++ ) {
		parser.ExpectTokenString( "frame" );
		num = parser.ParseInt();
		if ( num != i ) {
			parser.Error( "Expected frame number %d", i );
		}
		parser.ExpectTokenString( "{" );
		
		for( j = 0; j < numAnimatedComponents; j++, componentPtr++ ) {
			*componentPtr = parser.ParseFloat();
		}

		parser.ExpectTokenString( "}" );
	}

	// get total move delta
	if ( !numAnimatedComponents ) {
		totaldelta.Zero();
	} else {
		componentPtr = &componentFrames[ jointInfo[ 0 ].firstComponent ];
		if ( jointInfo[ 0 ].animBits & ANIM_TX ) {
			for( i = 0; i < numFrames; i++ ) {
				componentPtr[ numAnimatedComponents * i ] -= baseFrame[ 0 ].t.x;
			}
			totaldelta.x = componentPtr[ numAnimatedComponents * ( numFrames - 1 ) ];
			componentPtr++;
		} else {
			totaldelta.x = 0.0f;
		}
		if ( jointInfo[ 0 ].animBits & ANIM_TY ) {
			for( i = 0; i < numFrames; i++ ) {
				componentPtr[ numAnimatedComponents * i ] -= baseFrame[ 0 ].t.y;
			}
			totaldelta.y = componentPtr[ numAnimatedComponents * ( numFrames - 1 ) ];
			componentPtr++;
		} else {
			totaldelta.y = 0.0f;
		}
		if ( jointInfo[ 0 ].animBits & ANIM_TZ ) {
			for( i = 0; i < numFrames; i++ ) {
				componentPtr[ numAnimatedComponents * i ] -= baseFrame[ 0 ].t.z;
			}
			totaldelta.z = componentPtr[ numAnimatedComponents * ( numFrames - 1 ) ];
		} else {
			totaldelta.z = 0.0f;
		}
	}
	baseFrame[ 0 ].t.Zero();

	// we don't count last frame because it would cause a 1 frame pause at the end
	// (the frame and rate limits above keep this inside an int)
	animLength = ( ( numFrames - 1 ) * 1000 + frameRate - 1 ) / frameRate;

	if ( g_writeGeneratedAnimCache.GetBool() ) {
		WriteGeneratedAnim( filename );
	}

	// done
	return true;
}

/*
====================
idMD5Anim::IncreaseRefs
====================
*/
void idMD5Anim::IncreaseRefs( void ) const {
	ref_count++;
}

/*
====================
idMD5Anim::DecreaseRefs
====================
*/
void idMD5Anim::DecreaseRefs( void ) const {
	ref_count--;
}

/*
====================
idMD5Anim::NumRefs
====================
*/
int idMD5Anim::NumRefs( void ) const {
	return ref_count;
}

/*
====================
idMD5Anim::GetFrameBlend
====================
*/
void idMD5Anim::GetFrameBlend( int framenum, frameBlend_t &frame ) const {
	frame.cycleCount	= 0;
	frame.backlerp		= 0.0f;
	frame.frontlerp		= 1.0f;

	// frame 1 is first frame
	framenum--;
	if ( framenum < 0 ) {
		framenum = 0;
	} else if ( framenum >= numFrames ) {
		framenum = numFrames - 1;
	}

	frame.frame1 = framenum;
	frame.frame2 = framenum;
}

/*
====================
idMD5Anim::ConvertTimeToFrame
====================
*/
void idMD5Anim::ConvertTimeToFrame( int time, int cyclecount, frameBlend_t &frame ) const {
	int frameTime;
	int frameNum;

	if ( numFrames <= 1 ) {
		frame.frame1		= 0;
		frame.frame2		= 0;
		frame.backlerp		= 0.0f;
		frame.frontlerp		= 1.0f;
		frame.cycleCount	= 0;
		return;
	}

	if ( time <= 0 ) {
		frame.frame1		= 0;
		frame.frame2		= 1;
		frame.backlerp		= 0.0f;
		frame.frontlerp		= 1.0f;
		frame.cycleCount	= 0;
		return;
	}
	
	frameTime			= time * frameRate;
	frameNum			= frameTime / 1000;
	frame.cycleCount	= frameNum / ( numFrames - 1 );

	if ( ( cyclecount > 0 ) && ( frame.cycleCount >= cyclecount ) ) {
		frame.cycleCount	= cyclecount - 1;
		frame.frame1		= numFrames - 1;
		frame.frame2		= frame.frame1;
		frame.backlerp		= 0.0f;
		frame.frontlerp		= 1.0f;
		return;
	}
	
	frame.frame1 = frameNum % ( numFrames - 1 );
	frame.frame2 = frame.frame1 + 1;
	if ( frame.frame2 >= numFrames ) {
		frame.frame2 = 0;
	}

	frame.backlerp	= ( frameTime % 1000 ) * 0.001f;
	frame.frontlerp	= 1.0f - frame.backlerp;
}

/*
====================
idMD5Anim::GetOrigin
====================
*/
void idMD5Anim::GetOrigin( idVec3 &offset, int time, int cyclecount ) const {
	frameBlend_t frame;

	offset = baseFrame[ 0 ].t;
	if ( !( jointInfo[ 0 ].animBits & ( ANIM_TX | ANIM_TY | ANIM_TZ ) ) ) {
		// just use the baseframe		
		return;
	}

	ConvertTimeToFrame( time, cyclecount, frame );

	const float *componentPtr1 = &componentFrames[ numAnimatedComponents * frame.frame1 + jointInfo[ 0 ].firstComponent ];
	const float *componentPtr2 = &componentFrames[ numAnimatedComponents * frame.frame2 + jointInfo[ 0 ].firstComponent ];

	if ( jointInfo[ 0 ].animBits & ANIM_TX ) {
		offset.x = *componentPtr1 * frame.frontlerp + *componentPtr2 * frame.backlerp;
		componentPtr1++;
		componentPtr2++;
	}

	if ( jointInfo[ 0 ].animBits & ANIM_TY ) {
		offset.y = *componentPtr1 * frame.frontlerp + *componentPtr2 * frame.backlerp;
		componentPtr1++;
		componentPtr2++;
	}

	if ( jointInfo[ 0 ].animBits & ANIM_TZ ) {
		offset.z = *componentPtr1 * frame.frontlerp + *componentPtr2 * frame.backlerp;
	}

	if ( frame.cycleCount ) {
		offset += totaldelta * ( float )frame.cycleCount;
	}
}

/*
====================
idMD5Anim::GetOriginRotation
====================
*/
void idMD5Anim::GetOriginRotation( idQuat &rotation, int time, int cyclecount ) const {
	frameBlend_t	frame;
	int				animBits;
	
	animBits = jointInfo[ 0 ].animBits;
	if ( !( animBits & ( ANIM_QX | ANIM_QY | ANIM_QZ ) ) ) {
		// just use the baseframe		
		rotation = baseFrame[ 0 ].q;
		return;
	}

	ConvertTimeToFrame( time, cyclecount, frame );

	const float	*jointframe1 = &componentFrames[ numAnimatedComponents * frame.frame1 + jointInfo[ 0 ].firstComponent ];
	const float	*jointframe2 = &componentFrames[ numAnimatedComponents * frame.frame2 + jointInfo[ 0 ].firstComponent ];

	if ( animBits & ANIM_TX ) {
		jointframe1++;
		jointframe2++;
	}

	if ( animBits & ANIM_TY ) {
		jointframe1++;
		jointframe2++;
	}

	if ( animBits & ANIM_TZ ) {
		jointframe1++;
		jointframe2++;
	}

	idQuat q1;
	idQuat q2;

	switch( animBits & (ANIM_QX|ANIM_QY|ANIM_QZ) ) {
		case ANIM_QX:
			q1.x = jointframe1[0];
			q2.x = jointframe2[0];
			q1.y = baseFrame[ 0 ].q.y;
			q2.y = q1.y;
			q1.z = baseFrame[ 0 ].q.z;
			q2.z = q1.z;
			q1.w = q1.CalcW();
			q2.w = q2.CalcW();
			break;
		case ANIM_QY:
			q1.y = jointframe1[0];
			q2.y = jointframe2[0];
			q1.x = baseFrame[ 0 ].q.x;
			q2.x = q1.x;
			q1.z = baseFrame[ 0 ].q.z;
			q2.z = q1.z;
			q1.w = q1.CalcW();
			q2.w = q2.CalcW();
			break;
		case ANIM_QZ:
			q1.z = jointframe1[0];
			q2.z = jointframe2[0];
			q1.x = baseFrame[ 0 ].q.x;
			q2.x = q1.x;
			q1.y = baseFrame[ 0 ].q.y;
			q2.y = q1.y;
			q1.w = q1.CalcW();
			q2.w = q2.CalcW();
			break;
		case ANIM_QX|ANIM_QY:
			q1.x = jointframe1[0];
			q1.y = jointframe1[1];
			q2.x = jointframe2[0];
			q2.y = jointframe2[1];
			q1.z = baseFrame[ 0 ].q.z;
			q2.z = q1.z;
			q1.w = q1.CalcW();
			q2.w = q2.CalcW();
			break;
		case ANIM_QX|ANIM_QZ:
			q1.x = jointframe1[0];
			q1.z = jointframe1[1];
			q2.x = jointframe2[0];
			q2.z = jointframe2[1];
			q1.y = baseFrame[ 0 ].q.y;
			q2.y = q1.y;
			q1.w = q1.CalcW();
			q2.w = q2.CalcW();
			break;
		case ANIM_QY|ANIM_QZ:
			q1.y = jointframe1[0];
			q1.z = jointframe1[1];
			q2.y = jointframe2[0];
			q2.z = jointframe2[1];
			q1.x = baseFrame[ 0 ].q.x;
			q2.x = q1.x;
			q1.w = q1.CalcW();
			q2.w = q2.CalcW();
			break;
		case ANIM_QX|ANIM_QY|ANIM_QZ:
			q1.x = jointframe1[0];
			q1.y = jointframe1[1];
			q1.z = jointframe1[2];
			q2.x = jointframe2[0];
			q2.y = jointframe2[1];
			q2.z = jointframe2[2];
			q1.w = q1.CalcW();
			q2.w = q2.CalcW();
			break;
	}

	rotation.Slerp( q1, q2, frame.backlerp );
}

/*
====================
idMD5Anim::GetBounds
====================
*/
void idMD5Anim::GetBounds( idBounds &bnds, int time, int cyclecount ) const {
	frameBlend_t	frame;
	idVec3			offset;

	ConvertTimeToFrame( time, cyclecount, frame );

	bnds = bounds[ frame.frame1 ];
	bnds.AddBounds( bounds[ frame.frame2 ] );

	// origin position
	offset = baseFrame[ 0 ].t;
	if ( jointInfo[ 0 ].animBits & ( ANIM_TX | ANIM_TY | ANIM_TZ ) ) {
		const float *componentPtr1 = &componentFrames[ numAnimatedComponents * frame.frame1 + jointInfo[ 0 ].firstComponent ];
		const float *componentPtr2 = &componentFrames[ numAnimatedComponents * frame.frame2 + jointInfo[ 0 ].firstComponent ];

		if ( jointInfo[ 0 ].animBits & ANIM_TX ) {
			offset.x = *componentPtr1 * frame.frontlerp + *componentPtr2 * frame.backlerp;
			componentPtr1++;
			componentPtr2++;
		}

		if ( jointInfo[ 0 ].animBits & ANIM_TY ) {
			offset.y = *componentPtr1 * frame.frontlerp + *componentPtr2 * frame.backlerp;
			componentPtr1++;
			componentPtr2++;
		}

		if ( jointInfo[ 0 ].animBits & ANIM_TZ ) {
			offset.z = *componentPtr1 * frame.frontlerp + *componentPtr2 * frame.backlerp;
		}
	}

	bnds[ 0 ] -= offset;
	bnds[ 1 ] -= offset;
}

/*
====================
idMD5Anim::GetInterpolatedFrame
====================
*/
void idMD5Anim::GetInterpolatedFrame( frameBlend_t &frame, idJointQuat *joints, const int *index, int numIndexes ) const {
	int						i, numLerpJoints;
	const float				*frame1;
	const float				*frame2;
	const float				*jointframe1;
	const float				*jointframe2;
	const jointAnimInfo_t	*infoPtr;
	int						animBits;
	idJointQuat				*blendJoints;
	idJointQuat				*jointPtr;
	idJointQuat				*blendPtr;
	int						*lerpIndex;

	// copy the baseframe
	SIMDProcessor->Memcpy( joints, baseFrame.Ptr(), baseFrame.Num() * sizeof( baseFrame[ 0 ] ) );

	if ( !numAnimatedComponents ) {
		// just use the base frame
		return;
	}

	blendJoints = (idJointQuat *)_alloca16( baseFrame.Num() * sizeof( blendPtr[ 0 ] ) );
	lerpIndex = (int *)_alloca16( baseFrame.Num() * sizeof( lerpIndex[ 0 ] ) );
	numLerpJoints = 0;

	frame1 = &componentFrames[ frame.frame1 * numAnimatedComponents ];
	frame2 = &componentFrames[ frame.frame2 * numAnimatedComponents ];

	for ( i = 0; i < numIndexes; i++ ) {
		int j = index[i];
		jointPtr = &joints[j];
		blendPtr = &blendJoints[j];
		infoPtr = &jointInfo[j];

		animBits = infoPtr->animBits;
		if ( animBits ) {

			lerpIndex[numLerpJoints++] = j;

			jointframe1 = frame1 + infoPtr->firstComponent;
			jointframe2 = frame2 + infoPtr->firstComponent;

			switch( animBits & (ANIM_TX|ANIM_TY|ANIM_TZ) ) {
				case 0:
					blendPtr->t = jointPtr->t;
					break;
				case ANIM_TX:
					jointPtr->t.x = jointframe1[0];
					blendPtr->t.x = jointframe2[0];
					blendPtr->t.y = jointPtr->t.y;
					blendPtr->t.z = jointPtr->t.z;

					//HUMANHEAD rww - catch nan values
					assert(!FLOAT_IS_INVALID(jointPtr->t.x));
					assert(!FLOAT_IS_INVALID(blendPtr->t.x));
					assert(!FLOAT_IS_INVALID(blendPtr->t.y));
					assert(!FLOAT_IS_INVALID(blendPtr->t.z));
					//HUMANHEAD END

					jointframe1++;
					jointframe2++;
					break;
				case ANIM_TY:
					jointPtr->t.y = jointframe1[0];
					blendPtr->t.y = jointframe2[0];
					blendPtr->t.x = jointPtr->t.x;
					blendPtr->t.z = jointPtr->t.z;

					//HUMANHEAD rww - catch nan values
					assert(!FLOAT_IS_INVALID(jointPtr->t.y));
					assert(!FLOAT_IS_INVALID(blendPtr->t.y));
					assert(!FLOAT_IS_INVALID(blendPtr->t.x));
					assert(!FLOAT_IS_INVALID(blendPtr->t.z));
					//HUMANHEAD END

					jointframe1++;
					jointframe2++;
					break;
				case ANIM_TZ:
					jointPtr->t.z = jointframe1[0];
					blendPtr->t.z = jointframe2[0];
					blendPtr->t.x = jointPtr->t.x;
					blendPtr->t.y = jointPtr->t.y;

					//HUMANHEAD rww - catch nan values
					assert(!FLOAT_IS_INVALID(jointPtr->t.z));
					assert(!FLOAT_IS_INVALID(blendPtr->t.z));
					assert(!FLOAT_IS_INVALID(blendPtr->t.x));
					assert(!FLOAT_IS_INVALID(blendPtr->t.y));
					//HUMANHEAD END

					jointframe1++;
					jointframe2++;
					break;
				case ANIM_TX|ANIM_TY:
					jointPtr->t.x = jointframe1[0];
					jointPtr->t.y = jointframe1[1];
					blendPtr->t.x = jointframe2[0];
					blendPtr->t.y = jointframe2[1];
					blendPtr->t.z = jointPtr->t.z;

					//HUMANHEAD rww - catch nan values
					assert(!FLOAT_IS_INVALID(jointPtr->t.x));
					assert(!FLOAT_IS_INVALID(jointPtr->t.y));
					assert(!FLOAT_IS_INVALID(blendPtr->t.x));
					assert(!FLOAT_IS_INVALID(blendPtr->t.y));
					assert(!FLOAT_IS_INVALID(blendPtr->t.z));
					//HUMANHEAD END

					jointframe1 += 2;
					jointframe2 += 2;
					break;
				case ANIM_TX|ANIM_TZ:
					jointPtr->t.x = jointframe1[0];
					jointPtr->t.z = jointframe1[1];
					blendPtr->t.x = jointframe2[0];
					blendPtr->t.z = jointframe2[1];
					blendPtr->t.y = jointPtr->t.y;

					//HUMANHEAD rww - catch nan values
					assert(!FLOAT_IS_INVALID(jointPtr->t.x));
					assert(!FLOAT_IS_INVALID(jointPtr->t.z));
					assert(!FLOAT_IS_INVALID(blendPtr->t.x));
					assert(!FLOAT_IS_INVALID(blendPtr->t.z));
					assert(!FLOAT_IS_INVALID(blendPtr->t.y));
					//HUMANHEAD END

					jointframe1 += 2;
					jointframe2 += 2;
					break;
				case ANIM_TY|ANIM_TZ:
					jointPtr->t.y = jointframe1[0];
					jointPtr->t.z = jointframe1[1];
					blendPtr->t.y = jointframe2[0];
					blendPtr->t.z = jointframe2[1];
					blendPtr->t.x = jointPtr->t.x;

					//HUMANHEAD rww - catch nan values
					assert(!FLOAT_IS_INVALID(jointPtr->t.y));
					assert(!FLOAT_IS_INVALID(jointPtr->t.z));
					assert(!FLOAT_IS_INVALID(blendPtr->t.y));
					assert(!FLOAT_IS_INVALID(blendPtr->t.z));
					assert(!FLOAT_IS_INVALID(blendPtr->t.x));
					//HUMANHEAD END

					jointframe1 += 2;
					jointframe2 += 2;
					break;
				case ANIM_TX|ANIM_TY|ANIM_TZ:
					jointPtr->t.x = jointframe1[0];
					jointPtr->t.y = jointframe1[1];
					jointPtr->t.z = jointframe1[2];
					blendPtr->t.x = jointframe2[0];
					blendPtr->t.y = jointframe2[1];
					blendPtr->t.z = jointframe2[2];

					//HUMANHEAD rww - catch nan values
					assert(!FLOAT_IS_INVALID(jointPtr->t.x));
					assert(!FLOAT_IS_INVALID(jointPtr->t.y));
					assert(!FLOAT_IS_INVALID(jointPtr->t.z));
					assert(!FLOAT_IS_INVALID(blendPtr->t.x));
					assert(!FLOAT_IS_INVALID(blendPtr->t.y));
					assert(!FLOAT_IS_INVALID(blendPtr->t.z));
					//HUMANHEAD END

					jointframe1 += 3;
					jointframe2 += 3;
					break;
			}

			switch( animBits & (ANIM_QX|ANIM_QY|ANIM_QZ) ) {
				case 0:
					blendPtr->q = jointPtr->q;
					break;
				case ANIM_QX:
					jointPtr->q.x = jointframe1[0];
					blendPtr->q.x = jointframe2[0];
					blendPtr->q.y = jointPtr->q.y;
					blendPtr->q.z = jointPtr->q.z;
					jointPtr->q.w = jointPtr->q.CalcW();
					blendPtr->q.w = blendPtr->q.CalcW();

					//HUMANHEAD rww - catch nan values
					assert(!FLOAT_IS_INVALID(jointPtr->q.x));
					assert(!FLOAT_IS_INVALID(blendPtr->q.x));
					assert(!FLOAT_IS_INVALID(blendPtr->q.y));
					assert(!FLOAT_IS_INVALID(blendPtr->q.z));
					assert(!FLOAT_IS_INVALID(jointPtr->q.w));
					assert(!FLOAT_IS_INVALID(blendPtr->q.w));
					//HUMANHEAD END

					break;
				case ANIM_QY:
					jointPtr->q.y = jointframe1[0];
					blendPtr->q.y = jointframe2[0];
					blendPtr->q.x = jointPtr->q.x;
					blendPtr->q.z = jointPtr->q.z;
					jointPtr->q.w = jointPtr->q.CalcW();
					blendPtr->q.w = blendPtr->q.CalcW();

					//HUMANHEAD rww - catch nan values
					assert(!FLOAT_IS_INVALID(jointPtr->q.y));
					assert(!FLOAT_IS_INVALID(blendPtr->q.y));
					assert(!FLOAT_IS_INVALID(blendPtr->q.x));
					assert(!FLOAT_IS_INVALID(blendPtr->q.z));
					assert(!FLOAT_IS_INVALID(jointPtr->q.w));
					assert(!FLOAT_IS_INVALID(blendPtr->q.w));
					//HUMANHEAD END

					break;
				case ANIM_QZ:
					jointPtr->q.z = jointframe1[0];
					blendPtr->q.z = jointframe2[0];
					blendPtr->q.x = jointPtr->q.x;
					blendPtr->q.y = jointPtr->q.y;
					jointPtr->q.w = jointPtr->q.CalcW();
					blendPtr->q.w = blendPtr->q.CalcW();

					//HUMANHEAD rww - catch nan values
					assert(!FLOAT_IS_INVALID(jointPtr->q.z));
					assert(!FLOAT_IS_INVALID(blendPtr->q.z));
					assert(!FLOAT_IS_INVALID(blendPtr->q.x));
					assert(!FLOAT_IS_INVALID(blendPtr->q.y));
					assert(!FLOAT_IS_INVALID(jointPtr->q.w));
					assert(!FLOAT_IS_INVALID(blendPtr->q.w));
					//HUMANHEAD END

					break;
				case ANIM_QX|ANIM_QY:
					jointPtr->q.x = jointframe1[0];
					jointPtr->q.y = jointframe1[1];
					blendPtr->q.x = jointframe2[0];
					blendPtr->q.y = jointframe2[1];
					blendPtr->q.z = jointPtr->q.z;
					jointPtr->q.w = jointPtr->q.CalcW();
					blendPtr->q.w = blendPtr->q.CalcW();

					//HUMANHEAD rww - catch nan values
					assert(!FLOAT_IS_INVALID(jointPtr->q.x));
					assert(!FLOAT_IS_INVALID(jointPtr->q.y));
					assert(!FLOAT_IS_INVALID(blendPtr->q.x));
					assert(!FLOAT_IS_INVALID(blendPtr->q.y));
					assert(!FLOAT_IS_INVALID(blendPtr->q.z));
					assert(!FLOAT_IS_INVALID(jointPtr->q.w));
					assert(!FLOAT_IS_INVALID(blendPtr->q.w));
					//HUMANHEAD END

					break;
				case ANIM_QX|ANIM_QZ:
					jointPtr->q.x = jointframe1[0];
					jointPtr->q.z = jointframe1[1];
					blendPtr->q.x = jointframe2[0];
					blendPtr->q.z = jointframe2[1];
					blendPtr->q.y = jointPtr->q.y;
					jointPtr->q.w = jointPtr->q.CalcW();
					blendPtr->q.w = blendPtr->q.CalcW();

					//HUMANHEAD rww - catch nan values
					assert(!FLOAT_IS_INVALID(jointPtr->q.x));
					assert(!FLOAT_IS_INVALID(jointPtr->q.z));
					assert(!FLOAT_IS_INVALID(blendPtr->q.x));
					assert(!FLOAT_IS_INVALID(blendPtr->q.z));
					assert(!FLOAT_IS_INVALID(blendPtr->q.y));
					assert(!FLOAT_IS_INVALID(jointPtr->q.w));
					assert(!FLOAT_IS_INVALID(blendPtr->q.w));
					//HUMANHEAD END

					break;
				case ANIM_QY|ANIM_QZ:
					jointPtr->q.y = jointframe1[0];
					jointPtr->q.z = jointframe1[1];
					blendPtr->q.y = jointframe2[0];
					blendPtr->q.z = jointframe2[1];
					blendPtr->q.x = jointPtr->q.x;
					jointPtr->q.w = jointPtr->q.CalcW();
					blendPtr->q.w = blendPtr->q.CalcW();

					//HUMANHEAD rww - catch nan values
					assert(!FLOAT_IS_INVALID(jointPtr->q.y));
					assert(!FLOAT_IS_INVALID(jointPtr->q.z));
					assert(!FLOAT_IS_INVALID(blendPtr->q.y));
					assert(!FLOAT_IS_INVALID(blendPtr->q.z));
					assert(!FLOAT_IS_INVALID(blendPtr->q.x));
					assert(!FLOAT_IS_INVALID(jointPtr->q.w));
					assert(!FLOAT_IS_INVALID(blendPtr->q.w));
					//HUMANHEAD END

					break;
				case ANIM_QX|ANIM_QY|ANIM_QZ:
					jointPtr->q.x = jointframe1[0];
					jointPtr->q.y = jointframe1[1];
					jointPtr->q.z = jointframe1[2];
					blendPtr->q.x = jointframe2[0];
					blendPtr->q.y = jointframe2[1];
					blendPtr->q.z = jointframe2[2];
					jointPtr->q.w = jointPtr->q.CalcW();
					blendPtr->q.w = blendPtr->q.CalcW();

					//HUMANHEAD rww - catch nan values
					assert(!FLOAT_IS_INVALID(jointPtr->q.x));
					assert(!FLOAT_IS_INVALID(jointPtr->q.y));
					assert(!FLOAT_IS_INVALID(jointPtr->q.z));
					assert(!FLOAT_IS_INVALID(blendPtr->q.x));
					assert(!FLOAT_IS_INVALID(blendPtr->q.y));
					assert(!FLOAT_IS_INVALID(blendPtr->q.z));
					assert(!FLOAT_IS_INVALID(jointPtr->q.w));
					assert(!FLOAT_IS_INVALID(blendPtr->q.w));
					//HUMANHEAD END

					break;
			}
		}
	}

	SIMDProcessor->BlendJoints( joints, blendJoints, frame.backlerp, lerpIndex, numLerpJoints );

	if ( frame.cycleCount ) {
		joints[ 0 ].t += totaldelta * ( float )frame.cycleCount;
	}
}

/*
====================
idMD5Anim::GetSingleFrame
====================
*/
void idMD5Anim::GetSingleFrame( int framenum, idJointQuat *joints, const int *index, int numIndexes ) const {
	int						i;
	const float				*frame;
	const float				*jointframe;
	int						animBits;
	idJointQuat				*jointPtr;
	const jointAnimInfo_t	*infoPtr;

	// copy the baseframe
	SIMDProcessor->Memcpy( joints, baseFrame.Ptr(), baseFrame.Num() * sizeof( baseFrame[ 0 ] ) );

	if ( ( framenum == 0 ) || !numAnimatedComponents ) {
		// just use the base frame
		return;
	}

	frame = &componentFrames[ framenum * numAnimatedComponents ];

	for ( i = 0; i < numIndexes; i++ ) {
		int j = index[i];
		jointPtr = &joints[j];
		infoPtr = &jointInfo[j];

		animBits = infoPtr->animBits;
		if ( animBits ) {

			jointframe = frame + infoPtr->firstComponent;

			if ( animBits & (ANIM_TX|ANIM_TY|ANIM_TZ) ) {

				if ( animBits & ANIM_TX ) {
					jointPtr->t.x = *jointframe++;
				}

				if ( animBits & ANIM_TY ) {
					jointPtr->t.y = *jointframe++;
				}

				if ( animBits & ANIM_TZ ) {
					jointPtr->t.z = *jointframe++;
				}
			}

			if ( animBits & (ANIM_QX|ANIM_QY|ANIM_QZ) ) {

				if ( animBits & ANIM_QX ) {
					jointPtr->q.x = *jointframe++;
				}

				if ( animBits & ANIM_QY ) {
					jointPtr->q.y = *jointframe++;
				}

				if ( animBits & ANIM_QZ ) {
					jointPtr->q.z = *jointframe;
				}

				jointPtr->q.w = jointPtr->q.CalcW();
			}
		}
	}
}

/*
====================
idMD5Anim::CheckModelHierarchy
====================
*/
void idMD5Anim::CheckModelHierarchy( const idRenderModel *model ) const {
	int	i;
	int	jointNum;
	int	parent;

	if ( jointInfo.Num() != model->NumJoints() ) {
		gameLocal.Error( "Model '%s' has different # of joints than anim '%s'", model->Name(), name.c_str() );
	}

	const idMD5Joint *modelJoints = model->GetJoints();
	for( i = 0; i < jointInfo.Num(); i++ ) {
		jointNum = jointInfo[ i ].nameIndex;
		if ( modelJoints[ i ].name != animationLib.JointName( jointNum ) ) {
			gameLocal.Error( "Model '%s''s joint names don't match anim '%s''s", model->Name(), name.c_str() );
		}
		if ( modelJoints[ i ].parent ) {
			parent = modelJoints[ i ].parent - modelJoints;
		} else {
			parent = -1;
		}
		if ( parent != jointInfo[ i ].parentNum ) {
			gameLocal.Error( "Model '%s' has different joint hierarchy than anim '%s'", model->Name(), name.c_str() );
		}
	}
}

/***********************************************************************

	idAnimManager

***********************************************************************/

/*
====================
idAnimManager::idAnimManager
====================
*/
idAnimManager::idAnimManager() {
}

/*
====================
idAnimManager::~idAnimManager
====================
*/
idAnimManager::~idAnimManager() {
	Shutdown();
}

/*
====================
idAnimManager::Shutdown
====================
*/
void idAnimManager::Shutdown( void ) {
	animations.DeleteContents();
	jointnames.Clear();
	jointnamesHash.Free();
}

/*
====================
idAnimManager::GetAnim
====================
*/
idMD5Anim *idAnimManager::GetAnim( const char *name ) {
	idMD5Anim **animptrptr;
	idMD5Anim *anim;

	// see if it has been asked for before
	animptrptr = NULL;
	if ( animations.Get( name, &animptrptr ) ) {
		anim = *animptrptr;
	} else {
		idStr extension;
		idStr filename = name;

		filename.ExtractFileExtension( extension );
		if ( extension != MD5_ANIM_EXT ) {
			return NULL;
		}

		// HUMANHEAD nla - Create our version of the class instead of theirs
		anim = new hhMD5Anim();
		// HUMANHEAD END
		if ( !anim->LoadAnim( filename ) ) {
			gameLocal.Warning( "Couldn't load anim: '%s'", filename.c_str() );
			delete anim;
			anim = NULL;
		}
		animations.Set( filename, anim );
	}

	return anim;
}

/*
================
idAnimManager::ReloadAnims
================
*/
void idAnimManager::ReloadAnims( void ) {
	int			i;
	idMD5Anim	**animptr;

	for( i = 0; i < animations.Num(); i++ ) {
		animptr = animations.GetIndex( i );
		if ( animptr && *animptr ) {
			( *animptr )->Reload();
		}
	}
}

/*
================
idAnimManager::ReloadGeneratedCacheAnims

Re-derives from source every resident animation that was decoded from the
generated animation cache, and returns how many it reloaded. idGameLocal::LoadMap
calls it once the filesystem refuses generated-cache reads (a pure lock or
fs_restrict), so an animation decoded before the lock cannot outlive it. The
cache is refused by then, so LoadAnim parses the source from the pure paks;
reloading in place keeps every model definition's pointer valid.
================
*/
int idAnimManager::ReloadGeneratedCacheAnims( void ) {
	int reloaded = 0;
	for ( int i = 0; i < animations.Num(); i++ ) {
		idMD5Anim **animptr = animations.GetIndex( i );
		if ( animptr == NULL || *animptr == NULL || !( *animptr )->FromGeneratedCache() ) {
			continue;
		}
		const idStr animName = ( *animptr )->Name();
		if ( !( *animptr )->Reload() ) {
			gameLocal.Warning( "Could not reload animation '%s' from its source", animName.c_str() );
		}
		reloaded++;
	}
	return reloaded;
}

/*
================
idAnimManager::JointIndex
================
*/
int	idAnimManager::JointIndex( const char *name ) {
	int i, hash;

	hash = jointnamesHash.GenerateKey( name );
	for ( i = jointnamesHash.First( hash ); i != -1; i = jointnamesHash.Next( i ) ) {
		if ( jointnames[i].Cmp( name ) == 0 ) {
			return i;
		}
	}

	i = jointnames.Append( name );
	jointnamesHash.Add( hash, i );
	return i;
}

/*
================
idAnimManager::JointName
================
*/
const char *idAnimManager::JointName( int index ) const {
	return jointnames[ index ];
}

/*
================
idAnimManager::ListAnims
================
*/
void idAnimManager::ListAnims( void ) const {
	int			i;
	idMD5Anim	**animptr;
	idMD5Anim	*anim;
	size_t		size;
	size_t		s;
	size_t		namesize;
	int			num;

	num = 0;
	size = 0;
	for( i = 0; i < animations.Num(); i++ ) {
		animptr = animations.GetIndex( i );
		if ( animptr && *animptr ) {
			anim = *animptr;
			s = anim->Size();
			gameLocal.Printf( "%8d bytes : %2d refs : %s\n", s, anim->NumRefs(), anim->Name() );
			size += s;
			num++;
		}
	}

	namesize = jointnames.Size() + jointnamesHash.Size();
	for( i = 0; i < jointnames.Num(); i++ ) {
		namesize += jointnames[ i ].Size();
	}

	gameLocal.Printf( "\n%d memory used in %d anims\n", size, num );
	gameLocal.Printf( "%d memory used in %d joint names\n", namesize, jointnames.Num() );
}

// HUMANHEAD pdm: print animation memory statistics
void idAnimManager::PrintMemInfo( MemInfo_t *mi ) {
	int i, j, totalMem = 0;
	int *sortIndex;
	idFile *f;
	idMD5Anim	**animptr1;
	idMD5Anim	**animptr2;
	idMD5Anim	*anim;
	size_t		s1, s2;

	f = fileSystem->OpenFileWrite( mi->filebase + "_anims.txt" );
	if ( !f ) {
		return;
	}

	// sort first
	sortIndex = new int[ animations.Num() ];

	for ( i = 0; i <  animations.Num(); i++ ) {
		sortIndex[i] = i;
	}

	for ( i = 0; i <  animations.Num() - 1; i++ ) {
		for ( j = i + 1; j <  animations.Num(); j++ ) {
			s1 = s2 = 0;
			animptr1 = animations.GetIndex( sortIndex[i] );
			animptr2 = animations.GetIndex( sortIndex[j] );
			if ( animptr1 && *animptr1 ) {
				s1 = (*animptr1)->Size();
			}
			if ( animptr2 && *animptr2 ) {
				s2 = (*animptr2)->Size();
			}
			if ( s1 < s2 ) {
				int temp = sortIndex[i];
				sortIndex[i] = sortIndex[j];
				sortIndex[j] = temp;
			}
		}
	}

	// print next
	for ( int i = 0 ; i < animations.Num() ; i++ ) {
		animptr1 = animations.GetIndex( sortIndex[i] );
		if ( animptr1 && *animptr1 ) {
			anim = *animptr1;
			s1 = anim->Size();
			f->Printf( "%s %d %s\n", idStr::FormatNumber( (int)s1 ).c_str(), anim->NumRefs(), anim->Name() );
			totalMem += s1;
		}
	}

	delete[] sortIndex;
	mi->animAssetsTotal = totalMem;

	f->Printf( "\nTotal anim bytes allocated: %s\n", idStr::FormatNumber( totalMem ).c_str() );
	fileSystem->CloseFile( f );
}

/*
================
idAnimManager::FlushUnusedAnims
================
*/
void idAnimManager::FlushUnusedAnims( void ) {
	int						i;
	idMD5Anim				**animptr;
	idList<idMD5Anim *>		removeAnims;
	
	for( i = 0; i < animations.Num(); i++ ) {
		animptr = animations.GetIndex( i );
		if ( animptr && *animptr ) {
			if ( ( *animptr )->NumRefs() <= 0 ) {
				removeAnims.Append( *animptr );
			}
		}
	}

	for( i = 0; i < removeAnims.Num(); i++ ) {
		animations.Remove( removeAnims[ i ]->Name() );
		delete removeAnims[ i ];
	}
}
