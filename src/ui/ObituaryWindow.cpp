// Copyright (C) 2026 DarkMatter Productions
// SPDX-License-Identifier: GPL-3.0-or-later
#include "DeviceContext.h"
#include "UserInterfaceLocal.h"
#include "ObituaryWindow.h"

/*
The feed's construction (docs/dev/prey-ui-visual-design.md, 12.1), in
640x480 units at the default type scale of 0.25. It is built as the
multiplayer HUD's standings box is (hud_mpmisc.guifragment), so the two
corners of the screen read as one family:

- A line is a box 15 u high, as wide as its content: 4 u of padding, the
  killer's name, the icon 12 u high (a weapon 24 u wide), the victim's
  name and 4 u more. Names are cut at 100 u.
- The box is the standings' black well at 0.5 inside a 1 u #66738C rim.
  Lines stack on a 14 u pitch, so neighbours share a rim and the feed reads
  as one table, stepped where the lines differ in width.
- A line naming the local player takes the scoreboard's own-row bar,
  #B3CCE6 at 0.2.
- Names are white with the HUD's drop shadow, the local player's deathmatch
  yellow (#FFCC1A); team games colour every name by team (#FF0000, #3380CC).
  Icons are HUD ink (#A0B2CA).
- A line fades in over 200 ms and out over its last 320 ms; the lines below
  glide up into the place it leaves, as the pickup column slides.
*/

static const float OBIT_ROW_HEIGHT		= 15.0f;
static const float OBIT_ROW_PITCH		= 14.0f;	// neighbours share their 1 u rim
static const float OBIT_ICON_HEIGHT		= 12.0f;
static const float OBIT_PADDING			= 4.0f;
static const float OBIT_SPACING			= 3.0f;
static const float OBIT_NAME_LIMIT		= 100.0f;
static const int   OBIT_ENTER_MS		= 200;
static const int   OBIT_EXIT_MS			= 320;
static const int   OBIT_HURRY_MS		= 200;
static const float OBIT_GLIDE_MS		= 60.0f;

static const idVec4 OBIT_WELL			( 0.0f, 0.0f, 0.0f, 0.5f );				// the standings box
static const idVec4 OBIT_RIM			( 0.4f, 0.45f, 0.55f, 1.0f );			// its rim, #66738C
static const idVec4 OBIT_SELF_BAR		( 0.702f, 0.8f, 0.902f, 0.2f );			// the scoreboard's own row
static const idVec4 OBIT_INK			( 0.627f, 0.698f, 0.792f, 1.0f );		// hud.ink
static const idVec4 OBIT_INK_BRIGHT		( 0.792f, 0.882f, 1.0f, 1.0f );			// hud.ink's highlight
static const idVec4 OBIT_NAME			( 1.0f, 1.0f, 1.0f, 1.0f );
static const idVec4 OBIT_NAME_SELF		( 1.0f, 0.8f, 0.102f, 1.0f );			// deathmatch yellow
static const idVec4 OBIT_TEAM_RED		( 1.0f, 0.0f, 0.0f, 1.0f );
static const idVec4 OBIT_TEAM_BLUE		( 0.2f, 0.502f, 0.8f, 1.0f );

static const int OBIT_SELF_KILLER		= 1;
static const int OBIT_SELF_VICTIM		= 2;

static float ObitEaseOut( float t ) {
	t = idMath::ClampFloat( 0.0f, 1.0f, t );
	const float inverse = 1.0f - t;
	return 1.0f - inverse * inverse * inverse;
}

static idVec4 ObitNameInk( int team, bool self ) {
	if ( team == 1 ) {
		return OBIT_TEAM_RED;
	}
	if ( team == 0 ) {
		return OBIT_TEAM_BLUE;
	}
	return self ? OBIT_NAME_SELF : OBIT_NAME;
}

static idVec4 ObitFaded( const idVec4 &color, float alpha ) {
	return idVec4( color.x, color.y, color.z, color.w * alpha );
}

idObituaryWindow::idObituaryWindow( idDeviceContext *context, idUserInterfaceLocal *owner )
	: idWindow( context, owner ), numLines( 0 ), maxLines( 5 ), lifeTime( 3000 ), lastDrawTime( 0 ) {
}

bool idObituaryWindow::ParseInternalVar( const char *name, idParser *src ) {
	if ( idStr::Icmp( name, "maxlines" ) == 0 ) {
		maxLines = idMath::ClampInt( 1, MAX_LINES - 1, src->ParseInt() );
		return true;
	}
	if ( idStr::Icmp( name, "lifetime" ) == 0 ) {
		lifeTime = idMath::ClampInt( OBIT_ENTER_MS + OBIT_EXIT_MS, 60000, src->ParseInt() );
		return true;
	}
	return idWindow::ParseInternalVar( name, src );
}

void idObituaryWindow::Clear() {
	for ( int i = 0; i < numLines; i++ ) {
		lines[ i ].killer.Clear();
		lines[ i ].victim.Clear();
	}
	numLines = 0;
}

void idObituaryWindow::RunNamedEvent( const char *eventName ) {
	if ( !idStr::Icmp( eventName, "obitPush" ) ) {
		Push( gui->GetStateInt( "obit_time", va( "%d", gui->GetTime() ) ) );
	} else if ( !idStr::Icmp( eventName, "obitReset" ) ) {
		Clear();
	}
	idWindow::RunNamedEvent( eventName );
}

void idObituaryWindow::Push( int now ) {
	// A full feed hurries its oldest line out; the newest never waits.
	int live = 0;
	for ( int i = 0; i < numLines; i++ ) {
		if ( lines[ i ].end - now > OBIT_HURRY_MS ) {
			live++;
		}
	}
	for ( int i = 0; i < numLines && live >= maxLines; i++ ) {
		if ( lines[ i ].end - now > OBIT_HURRY_MS ) {
			lines[ i ].end = now + OBIT_HURRY_MS;
			live--;
		}
	}
	if ( numLines == MAX_LINES ) {
		for ( int i = 1; i < numLines; i++ ) {
			lines[ i - 1 ] = lines[ i ];
		}
		numLines--;
	}

	line_t &line = lines[ numLines ];
	line.killer = gui->GetStateString( "obit_killer" );
	line.victim = gui->GetStateString( "obit_victim" );
	// Colour codes would fight the role colours below.
	line.killer.RemoveColors();
	line.victim.RemoveColors();
	const char *icon = gui->GetStateString( "obit_icon" );
	const char *badge = gui->GetStateString( "obit_badge" );
	line.icon = icon[ 0 ] ? declManager->FindMaterial( icon, false ) : NULL;
	line.badge = badge[ 0 ] ? declManager->FindMaterial( badge, false ) : NULL;
	line.self = gui->GetStateInt( "obit_self" );
	line.killerInk = ObitNameInk( gui->GetStateInt( "obit_killerTeam", "-1" ), ( line.self & OBIT_SELF_KILLER ) != 0 );
	line.victimInk = ObitNameInk( gui->GetStateInt( "obit_victimTeam", "-1" ), ( line.self & OBIT_SELF_VICTIM ) != 0 );
	line.start = now;
	line.end = now + lifeTime;
	line.y = numLines > 0 ? lines[ numLines - 1 ].y + OBIT_ROW_PITCH : 0.0f;
	line.measuredScale = 0.0f;
	numLines++;
}

// Cuts a name to the width it may take, marking the cut.
void idObituaryWindow::Truncate( idStr &name, float scale, float limit ) {
	if ( dc->TextWidth( name, scale, -1 ) <= limit ) {
		return;
	}
	const float mark = static_cast<float>( dc->TextWidth( "..", scale, -1 ) );
	while ( name.Length() > 1 && dc->TextWidth( name, scale, -1 ) + mark > limit ) {
		name.CapLength( name.Length() - 1 );
	}
	name.StripTrailingWhitespace();
	name += "..";
}

void idObituaryWindow::Measure( line_t &line, float scale ) {
	if ( line.measuredScale == scale ) {
		return;
	}
	Truncate( line.killer, scale, OBIT_NAME_LIMIT );
	Truncate( line.victim, scale, OBIT_NAME_LIMIT );
	line.killerWidth = line.killer.Length() ? static_cast<float>( dc->TextWidth( line.killer, scale, -1 ) ) : 0.0f;
	line.victimWidth = static_cast<float>( dc->TextWidth( line.victim, scale, -1 ) );
	float aspect = 1.0f;
	if ( line.icon != NULL && line.icon->GetImageHeight() > 0 ) {
		aspect = static_cast<float>( line.icon->GetImageWidth() ) / line.icon->GetImageHeight();
	}
	line.iconWidth = line.icon != NULL ? OBIT_ICON_HEIGHT * idMath::ClampFloat( 0.5f, 4.0f, aspect ) : 0.0f;
	// An image not yet resident reports no size; measure again on a later frame.
	line.measuredScale = ( line.icon == NULL || line.icon->GetImageHeight() > 0 ) ? scale : 0.0f;
}

void idObituaryWindow::DrawLine( const line_t &line, float left, float top, int time ) {
	const int age = time - line.start;
	const float enter = ObitEaseOut( static_cast<float>( age ) / OBIT_ENTER_MS );
	const int exitWindow = Min( OBIT_EXIT_MS, line.end - line.start );
	const float leave = idMath::ClampFloat( 0.0f, 1.0f, static_cast<float>( line.end - time ) / exitWindow );
	const float alpha = enter * leave;
	if ( alpha <= 0.0f ) {
		return;
	}
	const bool killer = line.killer.Length() > 0;
	const float contentWidth = ( killer ? line.killerWidth + OBIT_SPACING : 0.0f ) + line.iconWidth +
		OBIT_SPACING + line.victimWidth;
	// One more unit trailing for the names' drop shadow.
	const float boxWidth = OBIT_PADDING * 2.0f + 1.0f + contentWidth;

	// The standings box: a black well in a steel rim, the own-row bar inside it.
	dc->DrawFilledRect( left, top, boxWidth, OBIT_ROW_HEIGHT, ObitFaded( OBIT_WELL, alpha ) );
	if ( line.self ) {
		dc->DrawFilledRect( left + 1.0f, top + 1.0f, boxWidth - 2.0f, OBIT_ROW_HEIGHT - 2.0f, ObitFaded( OBIT_SELF_BAR, alpha ) );
	}
	dc->DrawRect( left, top, boxWidth, OBIT_ROW_HEIGHT, 1.0f, ObitFaded( OBIT_RIM, alpha ) );

	// Vertical centring seats the font's full height, accents included, so the
	// capitals sit low: lift them to the box's middle (2 u at the 0.25 scale).
	const float textScale = this->textScale;
	const float textTop = top - 2.0f * textScale / 0.25f;
	float x = left + OBIT_PADDING;
	if ( killer ) {
		dc->DrawText( line.killer, textScale, 3, ObitFaded( line.killerInk, alpha ),
			idRectangle( x, textTop, line.killerWidth + 4.0f, OBIT_ROW_HEIGHT ), false, -1, false, NULL, 0, 0, 1 );
		x += line.killerWidth + OBIT_SPACING;
	}
	if ( line.icon != NULL ) {
		const float iconTop = top + ( OBIT_ROW_HEIGHT - OBIT_ICON_HEIGHT ) * 0.5f;
		dc->DrawMaterial( x, iconTop, line.iconWidth, OBIT_ICON_HEIGHT, line.icon, ObitFaded( OBIT_INK, alpha ) );
		if ( line.badge != NULL ) {
			const float badge = OBIT_ICON_HEIGHT * 0.66f;
			dc->DrawMaterial( x + line.iconWidth - badge * 0.55f, iconTop - 1.0f, badge, badge, line.badge,
				ObitFaded( OBIT_INK_BRIGHT, alpha ) );
		}
		x += line.iconWidth;
	}
	x += OBIT_SPACING;
	dc->DrawText( line.victim, textScale, 3, ObitFaded( line.victimInk, alpha ),
		idRectangle( x, textTop, line.victimWidth + 4.0f, OBIT_ROW_HEIGHT ), false, -1, false, NULL, 0, 0, 1 );
}

void idObituaryWindow::Draw( int time, float x, float y ) {
	if ( time < lastDrawTime - 1000 ) {
		// A new time base (a restart, a new map's GUI clock): nothing carries over.
		Clear();
	}
	const float elapsed = idMath::ClampFloat( 0.0f, 100.0f, static_cast<float>( time - lastDrawTime ) );
	lastDrawTime = time;

	int kept = 0;
	for ( int i = 0; i < numLines; i++ ) {
		if ( lines[ i ].end > time ) {
			if ( kept != i ) {
				lines[ kept ] = lines[ i ];
			}
			kept++;
		}
	}
	for ( int i = kept; i < numLines; i++ ) {
		lines[ i ].killer.Clear();
		lines[ i ].victim.Clear();
	}
	numLines = kept;
	if ( numLines == 0 ) {
		return;
	}

	SetFont();
	const float scale = textScale;
	const float glide = 1.0f - idMath::Exp( -elapsed / OBIT_GLIDE_MS );
	float slot = 0.0f;
	for ( int i = 0; i < numLines; i++ ) {
		line_t &line = lines[ i ];
		Measure( line, scale );
		line.y += ( slot - line.y ) * glide;
		if ( idMath::Fabs( slot - line.y ) < 0.05f ) {
			line.y = slot;
		}
		DrawLine( line, drawRect.x, drawRect.y + line.y, time );
		slot += OBIT_ROW_PITCH;
	}
}
