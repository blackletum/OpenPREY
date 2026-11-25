
#include "../idlib/precompiled.h"
#pragma hdrstop

#include "prey_local.h"

#define LETTERBOX_HEIGHT_TOP	50
#define LETTERBOX_HEIGHT_BOTTOM	50

const int IMPULSE_DELAY = 150;

// openPR06: the weapon-examine depth of field (UpdateWeaponExamineFocus).
// The focus pulls in over the first and lets go over the last part of the
// initialPickup anim, so the world is sharp again as the weapon comes up.
static const float WEAPON_EXAMINE_FOCUS_IN_SEC = 0.4f;
static const float WEAPON_EXAMINE_FOCUS_OUT_SEC = 0.6f;
// roughly where the examine anims hold the weapon; the renderer keeps the
// depth-hacked view weapon sharp whatever this is (VIEW_DOF_SHARP_VIEW_WEAPON)
static const float WEAPON_EXAMINE_FOCUS_DISTANCE = 16.0f;
// the thin lens the renderer is asked for; the f-number is chosen per frame
// so the far scene's blur reaches r_depthOfFieldRadius
static const float WEAPON_EXAMINE_FOCAL_LENGTH_MM = 50.0f;

idCVar r_depthOfFieldRadius( "r_depthOfFieldRadius", "9", CVAR_GAME | CVAR_ARCHIVE | CVAR_FLOAT,
	"widest blur of the weapon-examine depth of field, in pixels of a 1080-line view; 0 turns it off (r_depthOfField turns off all depth of field)", 0.0f, 32.0f );

//HUMANHEAD rww - render demo madness
#if _HH_RENDERDEMO_HACKS
	void RENDER_DEMO_VIEWRENDER(const renderView_t *view, const hhPlayerView *pView) {
		if (!view) {
			return;
		}

		const renderView_t *v = view;

		if (pView) {
			static renderView_t hackedView = *view;
			hackedView.viewaxis = hackedView.viewaxis * pView->ShakeAxis();

			v = &hackedView;
		}

		renderSystem->LogViewRender(v);
	}

	void RENDER_DEMO_VIEWRENDER_END(void) {
		renderSystem->LogViewRender(NULL);
	}
#endif
//HUMANHEAD END

hhPlayerView::hhPlayerView() {
	// HUMANHEAD pdm: we don't use the tunnel vision or armor
	bLetterBox = false;
	letterboxMaterial = declManager->FindMaterial( "_black" );
	dirDmgLeftMaterial = declManager->FindMaterial( "textures/interface/directionalDamageLeft" );
	dirDmgFrontMaterial = declManager->FindMaterial( "textures/interface/directionalDamageFront" );
	spiritMaterial = NULL;
	viewOverlayMaterial = NULL;
	viewOverlayColor = colorWhite;
	voTotalTime = -1;
	voRequiresScratchBuffer = false;
	viewOffset.Zero();

	kickSpeed.Zero();
	kickLastTime = 0;
	hurtValue = 100.f;

	vrComfort = 0.0f;
	vrComfortYaw = 0.0f;
	vrComfortTime = 0;
	vrComfortGameTime = 0;
	vrAimMarked = false;

	weaponExamineFocus = 0.0f;
	weaponExamineFocusTime = 0;
}

void hhPlayerView::Save(idSaveGame *savefile) const {
	idPlayerView::Save( savefile );

	savefile->WriteBool( bLetterBox );
	savefile->WriteFloat( mbAmplitude );
	savefile->WriteInt( mbFinishTime );
	savefile->WriteInt( mbTotalTime );
	savefile->WriteVec3( mbDirection );
	savefile->WriteVec3( viewOffset );
	savefile->WriteMaterial( viewOverlayMaterial );
	savefile->WriteVec4( viewOverlayColor );
	savefile->WriteInt( voFinishTime );
	savefile->WriteInt( voTotalTime );
	savefile->WriteInt( voRequiresScratchBuffer );
	savefile->WriteMaterial( letterboxMaterial );
	savefile->WriteMaterial( dirDmgLeftMaterial );
	savefile->WriteMaterial( dirDmgFrontMaterial );
	savefile->WriteMaterial( spiritMaterial );
	savefile->WriteVec3( lastDamageLocation );
	savefile->WriteInt( kickLastTime - gameLocal.time );
	savefile->WriteAngles( kickSpeed );
	savefile->WriteFloat( hurtValue );
}

void hhPlayerView::Restore( idRestoreGame *savefile ) {
	idPlayerView::Restore( savefile );

	savefile->ReadBool( bLetterBox );
	savefile->ReadFloat( mbAmplitude );
	savefile->ReadInt( mbFinishTime );
	savefile->ReadInt( mbTotalTime );
	savefile->ReadVec3( mbDirection );
	savefile->ReadVec3( viewOffset );
	savefile->ReadMaterial( viewOverlayMaterial );
	savefile->ReadVec4( viewOverlayColor );
	savefile->ReadInt( voFinishTime );
	savefile->ReadInt( voTotalTime );
	savefile->ReadInt( voRequiresScratchBuffer );
	savefile->ReadMaterial( letterboxMaterial );
	savefile->ReadMaterial( dirDmgLeftMaterial );
	savefile->ReadMaterial( dirDmgFrontMaterial );
	savefile->ReadMaterial( spiritMaterial );
	savefile->ReadVec3( lastDamageLocation );
	savefile->ReadInt( kickLastTime );
	kickLastTime += gameLocal.time;
	savefile->ReadAngles( kickSpeed );
	savefile->ReadFloat( hurtValue );
}

#define MAX_SCREEN_BLOBS_SYNC			2//MAX_SCREEN_BLOBS

//rwwFIXME it may be possible to remove a lot of this junk by assuring events happen on the client as they do on the server
//concerning damage etc.
void hhPlayerView::WriteToSnapshot( idBitMsgDelta &msg ) const {
	msg.WriteFloat(viewOffset.x);
	msg.WriteFloat(viewOffset.y);
	msg.WriteFloat(viewOffset.z);

	msg.WriteBits(voTotalTime, 32);
	msg.WriteBits(voFinishTime, 32);
	msg.WriteBits(voRequiresScratchBuffer, 1);

	if (viewOverlayMaterial) {
		msg.WriteLong(gameLocal.ServerRemapDecl(-1, DECL_MATERIAL, viewOverlayMaterial->Index()));
	}
	else {
		msg.WriteLong(-1);
	}

	//write screen blobs to snapshot
	for (int i = 0; i < MAX_SCREEN_BLOBS_SYNC; i++) {
		const screenBlob_t	*blob = &screenBlobs[i];

		//i'm disabling this since it might work against delta compression being effective
		/*
		if ( blob->finishTime <= gameLocal.time ) {
			msg.WriteBits(0, 1); //no need to do anymore, continue
			continue;
		}

		//otherwise continue writing
		msg.WriteBits(1, 1);
		*/

		if (blob->material) {
			msg.WriteLong(gameLocal.ServerRemapDecl(-1, DECL_MATERIAL, blob->material->Index()));
		}
		else {
			msg.WriteLong(-1);
		}

		msg.WriteFloat(blob->x);
		msg.WriteFloat(blob->y);
		msg.WriteFloat(blob->w);
		msg.WriteFloat(blob->h);

		msg.WriteFloat(blob->s1);
		msg.WriteFloat(blob->t1);
		msg.WriteFloat(blob->s2);
		msg.WriteFloat(blob->t2);

		msg.WriteBits(blob->finishTime, 32);
		msg.WriteBits(blob->startFadeTime, 32);

		msg.WriteFloat(blob->driftAmount);
	}

	//motion blur
	msg.WriteFloat(mbAmplitude);
	msg.WriteBits(mbFinishTime, 32);
	msg.WriteBits(mbTotalTime, 32);
	msg.WriteFloat(mbDirection.x);
	msg.WriteFloat(mbDirection.y);
	msg.WriteFloat(mbDirection.z);

	msg.WriteFloat(viewOverlayColor.w);
	msg.WriteFloat(viewOverlayColor.x);
	msg.WriteFloat(viewOverlayColor.y);
	msg.WriteFloat(viewOverlayColor.z);
}

void hhPlayerView::ReadFromSnapshot( const idBitMsgDelta &msg ) {
	viewOffset.x = msg.ReadFloat();
	viewOffset.y = msg.ReadFloat();
	viewOffset.z = msg.ReadFloat();

	voTotalTime = msg.ReadBits(32);
	voFinishTime = msg.ReadBits(32);
	voRequiresScratchBuffer = !!msg.ReadBits(1);

	int matIndex = msg.ReadLong();
	if (matIndex == -1) {
		viewOverlayMaterial = NULL;
	}
	else {
		int mappedIndex;

		if (voTotalTime != -1 && gameLocal.time >= voFinishTime) { //it's timed out so force it off
			voTotalTime = -1;
			voRequiresScratchBuffer = false;
			viewOverlayMaterial = NULL;
			mappedIndex = -1;
		}
		else {
			mappedIndex = gameLocal.ClientRemapDecl(DECL_MATERIAL, matIndex);
		}

		if (mappedIndex != -1) {
			viewOverlayMaterial = static_cast<const idMaterial *>(declManager->DeclByIndex(DECL_MATERIAL, mappedIndex));
		}
		else {
			viewOverlayMaterial = NULL;
		}
	}

	//read screen blobs from snapshot
	for (int i = 0; i < MAX_SCREEN_BLOBS_SYNC; i++) {
		screenBlob_t	*blob = &screenBlobs[i];

		//i'm disabling this since it might work against delta compression being effective
		/*
		bool valid = !!msg.ReadBits(1);
		if (!valid) {
			continue;
		}
		*/

		int blobMat = msg.ReadLong();
		if (blobMat == -1) {
			blob->material = NULL;
		}
		else {
			int mappedIndex = gameLocal.ClientRemapDecl(DECL_MATERIAL, blobMat);
			if (mappedIndex != -1) {
				blob->material = static_cast<const idMaterial *>(declManager->DeclByIndex(DECL_MATERIAL, mappedIndex));
			}
			else {
				blob->material = NULL;
			}
		}

		blob->x = msg.ReadFloat();
		blob->y = msg.ReadFloat();
		blob->w = msg.ReadFloat();
		blob->h = msg.ReadFloat();

		blob->s1 = msg.ReadFloat();
		blob->t1 = msg.ReadFloat();
		blob->s2 = msg.ReadFloat();
		blob->t2 = msg.ReadFloat();

		blob->finishTime = msg.ReadBits(32);
		blob->startFadeTime = msg.ReadBits(32);

		blob->driftAmount = msg.ReadFloat();
	}

	//motion blur
	mbAmplitude = msg.ReadFloat();
	mbFinishTime = msg.ReadBits(32);
	mbTotalTime = msg.ReadBits(32);
	mbDirection.x = msg.ReadFloat();
	mbDirection.y = msg.ReadFloat();
	mbDirection.z = msg.ReadFloat();

	viewOverlayColor.w = msg.ReadFloat();
	viewOverlayColor.x = msg.ReadFloat();
	viewOverlayColor.y = msg.ReadFloat();
	viewOverlayColor.z = msg.ReadFloat();
}

void hhPlayerView::ClearEffects() {
	idPlayerView::ClearEffects();

	// HUMANHEAD pdm
	mbFinishTime = gameLocal.time;

	weaponExamineFocus = 0.0f;
	weaponExamineFocusTime = gameLocal.time;
}


void hhPlayerView::SetDamageLoc(const idVec3 &damageLoc) {
	// This called before damageImpulse() so store the location
	lastDamageLocation = damageLoc;
}


//------------------------------------------------------
//
// DamageImpulse
//
// LocalKickDir is the direction of force in the player's coordinate system,
// which will determine the head kick direction
//------------------------------------------------------
void hhPlayerView::DamageImpulse( idVec3 localKickDir, const idDict *damageDef ) {

	// No screen damage effects when in third person
	if (pm_thirdPerson.GetBool()) {
		return;
	}

	if ( lastDamageTime > 0.0f && SEC2MS( lastDamageTime ) + IMPULSE_DELAY > gameLocal.time ) {
		// keep shotgun from obliterating the view
		return;
	}

	if (!player->InVehicle()) {
		//
		// Motion Blur effect
		//	HUMANHEAD pdm
		float mbTime = damageDef->GetFloat( "mb_time" );
		float severity = damageDef->GetFloat( "mb_amplitude" );
		if ( mbTime ) {
			idVec3 blurDirection;
			blurDirection.y = localKickDir[0];	// forward/back kick will blur vertically
			blurDirection.x = localKickDir[1];	// side kick will blur horizontally
			blurDirection.y += localKickDir[2];	// up/down kick will add to vertical
			MotionBlur(mbTime, severity, blurDirection);
		}

		//
		// head angle kick
		//
		float	kickTime = damageDef->GetFloat( "kick_time" );
		if ( kickTime ) {
			kickFinishTime = gameLocal.time + g_kickTime.GetFloat() * kickTime;

			// forward / back kick will pitch view
			kickAngles[0] = localKickDir[0];

			// side kick will yaw view
			kickAngles[1] = localKickDir[1]*0.5f;

			// up / down kick will pitch view
			kickAngles[0] += localKickDir[2];

			// roll will come from  side
			kickAngles[2] = localKickDir[1];

			float kickAmplitude = damageDef->GetFloat( "kick_amplitude" );
			if ( kickAmplitude ) {
				kickAngles *= kickAmplitude;
			}
		}

		//
		// HUMANHEAD: Screen blobs, changed functionality
		//
		float	blobTime = damageDef->GetFloat( "blob_time" );
		if ( blobTime ) {
			screenBlob_t	*blob = GetScreenBlob();
			blob->startFadeTime = gameLocal.time;
			blob->finishTime = gameLocal.time + blobTime * g_blobTime.GetFloat();

			const char *materialName = damageDef->GetString( "mtr_blob" );
			blob->material = declManager->FindMaterial( materialName );

			// Scale blob by 100% +/- blob_devscale%
			float scale = ( 256.0f + ( 256.0f*damageDef->GetFloat("blob_devscale")*gameLocal.random.CRandomFloat() ) ) / 256.0f;
			blob->w = damageDef->GetFloat( "blob_width" ) * g_blobSize.GetFloat() * scale;
			blob->h = damageDef->GetFloat( "blob_height" ) * g_blobSize.GetFloat() * scale;
			blob->s1 = 0;
			blob->t1 = 0;
			blob->s2 = 1;
			blob->t2 = 1;

			bool placedBlob = false;
			if (damageDef->GetBool("blob_projected") && player->renderView) {
				//rww - renderView null check added. I am not clear on when this may be null, but it apparently was. however, if a player were
				//to take damage before thinking, it seems very possible this would occur. the renderView will not be initialized until after
				//the first think.
				// Project hit location onto the virtual 640x480 screen used by DrawStretchPic.
				idVec3 localDamageLocation = hhUtils::ProjectOntoScreen(lastDamageLocation, *player->renderView);
				if ( localDamageLocation.z > 0.0f ) {
					const float xScale = 640.0f / Max( 1.0f, static_cast<float>( player->renderView->width ) );
					const float yScale = 480.0f / Max( 1.0f, static_cast<float>( player->renderView->height ) );
					blob->x = localDamageLocation.x * xScale - blob->w * 0.5f;
					blob->y = localDamageLocation.y * yScale - blob->h * 0.5f;
					placedBlob = true;
				}
			}
			if ( !placedBlob && damageDef->GetBool("blob_directional")) {
				// Directional blobs to show where damage is coming from (360 degree)
				float dirDist = damageDef->GetFloat("blob_dirdistance");
				blob->x = 320.0f + (dirDist * 320.0f * localKickDir.y) - (blob->w * 0.5f);
				blob->y = 240.0f + (dirDist * 240.0f * localKickDir.x) - (blob->h * 0.5f);
			}
			else if ( !placedBlob ) {
				// Place blob centered at (blob_x,blob_y)
				blob->x =  damageDef->GetFloat( "blob_x" ) - blob->w * 0.5f;
				blob->y =  damageDef->GetFloat( "blob_y" ) - blob->h * 0.5f;
			}

			// Deviate blob +/- (blob_devx,blob_devy)
			blob->x += damageDef->GetFloat( "blob_devx" ) * gameLocal.random.CRandomFloat();
			blob->y += damageDef->GetFloat( "blob_devy" ) * gameLocal.random.CRandomFloat();
		}
	}


	//
	// Global directional damage system
	//
/*
	const int directionDamageTime = 1000;
	screenBlob_t	*blob = GetScreenBlob();
	blob->startFadeTime = gameLocal.time;
	blob->finishTime = gameLocal.time + directionDamageTime;

	blob->s1 = 0;
	blob->t1 = 0;
	blob->s2 = 1;
	blob->t2 = 1;
	if (idMath::Fabs(localKickDir[0]) >= idMath::Fabs(localKickDir[1])) {
		// More in X direction
		blob->material = dirDmgFrontMaterial;
		blob->w = 500.0f;
		blob->h = 80.0f;
		blob->x = 320.0f - blob->w * 0.5f;
		if (localKickDir[0] >= 0.0f) {
			// From Rear
			blob->y = 480.0f - blob->h;
			idSwap(blob->t1, blob->t2);
		}
		else {
			// From Front
			blob->y = 0.0f;
		}
	}
	else {
		// More in Y direction
		blob->material = dirDmgLeftMaterial;
		blob->w = 80.0f;
		blob->h = 400.0f;
		blob->y = 240.0f - blob->h * 0.5f;
		if (localKickDir[1] >= 0.0f) {
			// From Right
			blob->x = 640.0f - blob->w;
			idSwap(blob->s1, blob->s2);
		}
		else {
			// From Left
			blob->x = 0.0f;
		}
	}
*/

	//
	// save lastDamageTime for tunnel vision accentuation
	//
	lastDamageTime = MS2SEC( gameLocal.time );

}

//------------------------------------------------------
// WeaponFireFeedback
// HUMANHEAD bjk
//------------------------------------------------------
void hhPlayerView::WeaponFireFeedback( const idDict *weaponDef ) {
	idAngles angles;
	idVec2 pitch, yaw, viewSpring;
	weaponDef->GetVec2( "recoilPitch", "0 0", pitch );
	weaponDef->GetVec2( "recoilYaw", "0 0", yaw );
	weaponDef->GetVec2( "viewSpring", "150 11", viewSpring );

	player->kickSpring = viewSpring.x;
	player->kickDamping = viewSpring.y;

	pitch.x = pitch.x + gameLocal.random.RandomFloat()*(pitch.y - pitch.x);
	yaw.x = yaw.x + gameLocal.random.RandomFloat()*(yaw.y - yaw.x);
	angles=idAngles(-pitch.x,-yaw.x,0);
	kickSpeed+=angles;
	assert(!FLOAT_IS_NAN(kickSpeed.pitch) && !FLOAT_IS_NAN(kickSpeed.yaw) && !FLOAT_IS_NAN(kickSpeed.roll));
}

//------------------------------------------------------
// AngleOffset
// HUMANHEAD bjk
//------------------------------------------------------
idAngles hhPlayerView::AngleOffset(float kickSpring, float kickDamping) {
	//HUMANHEAD rww - for other clients, do not add angle offset, it isn't predicted well
	if (gameLocal.isMultiplayer && !gameLocal.isServer && gameLocal.localClientNum != -1 && player && gameLocal.localClientNum != player->entityNumber) {
		kickSpeed.Zero();
		kickAngles.Zero();
		return kickAngles;
	}
	//HUMANHEAD END

	float frametime = (gameLocal.time - kickLastTime);
	kickLastTime = gameLocal.time;
	//kickAngles = kickAngles*(1-offset*kickSpeed)+kickBlendTo*offset*kickSpeed;
	//kickBlendTo = kickBlendTo*(1-offset*kickReturnSpeed)+ang*offset*kickReturnSpeed;

	//HUMANHEAD PCF rww 04/27/06 - these values can get unreasonable at times
#if 0
	for (int i = 0; i < 3; i++) {
		if (fabsf(kickSpeed[i]) > 9999.0f) {
			kickSpeed[i] = 0.0f;
		}
		if (fabsf(kickAngles[i]) > 9999.0f) {
			kickAngles[i] = 0.0f;
		}
	}
#endif
	if (frametime > 48.0f) {
		frametime = 48.0f;
	}
	//HUMANHEAD END

	assert(!FLOAT_IS_NAN(kickSpeed.pitch) && !FLOAT_IS_NAN(kickSpeed.yaw) && !FLOAT_IS_NAN(kickSpeed.roll));
	assert(!FLOAT_IS_NAN(kickAngles.pitch) && !FLOAT_IS_NAN(kickAngles.yaw) && !FLOAT_IS_NAN(kickAngles.roll));

	kickSpeed-=kickDamping*kickSpeed*frametime/1000;
	kickSpeed-=kickSpring*kickAngles*frametime/1000;

	if (gameLocal.isNewFrame) { //HUMANHEAD rww
		kickAngles+=kickSpeed*frametime/1000;
	}
	
	return kickAngles;
}

//------------------------------------------------------
// SingleView
//------------------------------------------------------
void hhPlayerView::SingleView( idUserInterface *hud, const renderView_t *view ) {
	// normal rendering

	if ( !view ) {
		return;
	}

	// place the sound origin for the player
	gameSoundWorld->PlaceListener( view->vieworg, view->viewaxis, player->entityNumber + 1, gameLocal.time, hud ? hud->State().GetString( "location" ) : "Undefined" );

	// hack the shake in at the very last moment, so it can't cause any consistency problems
	renderView_t	hackedView = *view;
	hackedView.viewaxis = hackedView.viewaxis * ShakeAxis();

	gameRenderWorld->RenderScene( &hackedView );

	if ( player->spectating ) {
		return;
	}

	// draw screen blobs
	if ( !pm_thirdPerson.GetBool() && !g_skipViewEffects.GetBool() ) {
		DrawScreenBlobs();
		UpdateViewOverlays();
		DrawViewOverlays( true );
	}

	// If this level has a sun corona, then attempt to draw it - CJR
	if ( !g_skipViewEffects.GetBool() && gameLocal.GetSunCorona() ) {
		gameLocal.GetSunCorona()->Draw( (hhPlayer *)player );
	}

	// test a single material drawn over everything
	if ( g_testPostProcess.GetString()[0] ) {
		const idMaterial *mtr = declManager->FindMaterial( g_testPostProcess.GetString(), false );
		if ( !mtr ) {
			common->Printf( "Material not found.\n" );
			g_testPostProcess.SetString( "" );
		} else {
			renderSystem->SetColor4( 1.0f, 1.0f, 1.0f, 1.0f );
			renderSystem->DrawStretchPic( 0.0f, 0.0f, 640.0f, 480.0f, 0.0f, 0.0f, 1.0f, 1.0f, mtr );
		}
	}
}

//------------------------------------------------------
// DrawScreenBlobs
//	the screen blobs, drifting once per drawn frame
//------------------------------------------------------
void hhPlayerView::DrawScreenBlobs( void ) {
	for ( int i = 0 ; i < MAX_SCREEN_BLOBS ; i++ ) {
		screenBlob_t	*blob = &screenBlobs[i];
		if ( blob->finishTime <= gameLocal.time ) {
			continue;
		}

		blob->y += blob->driftAmount;

		float	fade = (float)( blob->finishTime - gameLocal.time ) / ( blob->finishTime - blob->startFadeTime );
		if ( fade > 1.0f ) {
			fade = 1.0f;
		}
		if ( fade ) {
			renderSystem->SetColor4( 1,1,1,fade );
			renderSystem->DrawStretchPic( blob->x, blob->y, blob->w, blob->h, blob->s1, blob->t1, blob->s2, blob->t2, blob->material );
		}
	}
}

//------------------------------------------------------
// UpdateViewOverlays
//	times out the view overlay and eases the low-health tint, once per
//	drawn frame, so a VR frame that draws them into both eyes eases once
//------------------------------------------------------
void hhPlayerView::UpdateViewOverlays( void ) {
	// HUMANHEAD: CJR
	if ( voTotalTime != -1 ) { // Check if the viewOverlay should time out
		if ( gameLocal.time >= voFinishTime ) {
			voTotalTime = -1;
			voRequiresScratchBuffer = false;
			viewOverlayMaterial = NULL; // Remove the overlay
		}
	}

	if ( player->health > 0 && player->health < 25 && static_cast<hhPlayer*>(player)->IsSpiritOrDeathwalking()==false ) {
		hurtValue += 0.05f*(player->health - hurtValue);
		if( player->health > 30 )
			hurtValue = player->health;
	}
}

//------------------------------------------------------
// DrawViewOverlays
//	the full-view overlay and the low-health tint. An overlay that reads
//	the finished scene back (_scratch) is a flat-screen effect: a VR eye
//	(allowCapture false) leaves it out, as openQ4 does with double vision
//------------------------------------------------------
void hhPlayerView::DrawViewOverlays( bool allowCapture ) {
	//HUMANHEAD: aob
	if( viewOverlayMaterial && ( allowCapture || !voRequiresScratchBuffer ) ) {
		if ( voRequiresScratchBuffer ) {
			renderSystem->CaptureRenderToImage( "_scratch" );
		}
		renderSystem->SetColor4( viewOverlayColor[0], viewOverlayColor[1], viewOverlayColor[2], viewOverlayColor[3] );
		renderSystem->DrawStretchPic(0, 0, 640, 480, 0, 1, 1, 0, viewOverlayMaterial);
	}
	//HUMANHEAD END

	if ( player->health > 0 && player->health < 25 && static_cast<hhPlayer*>(player)->IsSpiritOrDeathwalking()==false ) {
		renderSystem->SetColor4( hurtValue/25.0f, 1, 1, 1 );
		renderSystem->DrawStretchPic(0, 0, 640, 480, 0, 1, 1, 0, hurtMaterial);
	}
}

/*
===============================================================================

	openPR06 VR: the first-person view once per headset eye.

	openQ4 builds this into its Quake 4 game code (idPlayerView::VRView); this
	is the Prey game's half of the same contract with the engine
	(src/framework/VRSystem.h). The engine owns the OpenXR session, paces the
	frame and turns the controllers into usercmds; the game renders each eye
	with SetVRRenderTarget and leaves the HUD, menus and cinematics on the
	virtual screen the headset shows in front of the player.

	Prey's player stands in its own gravity frame (wall-walking, gravity
	flips, the shuttle's dock rides), so the tracking space hangs off the eye
	in that frame rather than the world's: a tracked pose lands at
	eyeOrigin + pose.origin * yaw * eyeAxis, with eyeAxis the player's
	interpolated gravity frame (hhPlayer::GetEyeAxis) and yaw the tracking
	yaw, the same mapping hhPlayer uses to turn usercmd angles into its view.

===============================================================================
*/

//------------------------------------------------------
// GetVRView
//	the frame's tracked poses, when this view is one the eyes can show: the
//	local player's own first-person view. Cameras, cinematics, third person,
//	death and vehicles play flat on the virtual screen.
//------------------------------------------------------
bool hhPlayerView::GetVRView( vrFrameState_t &frame, float &trackingYaw ) {
	// the same rule holds the gun in the hand (hhPlayer::GetVRView)
	return player != NULL && static_cast<hhPlayer *>( player )->GetVRView( frame, trackingYaw );
}

//------------------------------------------------------
// VRZoomScale
//	a zoomed weapon magnifies each eye by the ratio of its field of view to
//	the player's own, eased as the flat screen eases it; the headset's field
//	of view itself cannot narrow
//------------------------------------------------------
float hhPlayerView::VRZoomScale( void ) {
	hhPlayer *hhplayer = static_cast<hhPlayer *>( player );
	const float defaultFov = player->DefaultFov();
	const float zoomedFov = hhplayer->GetZoomFov().GetCurrentValue( gameLocal.time );
	if ( zoomedFov <= 0.0f || zoomedFov >= defaultFov - 0.01f ) {
		return 1.0f;
	}
	const float scale = idMath::Tan( DEG2RAD( zoomedFov * 0.5f ) ) / idMath::Tan( DEG2RAD( defaultFov * 0.5f ) );
	return idMath::ClampFloat( 0.05f, 1.0f, scale );
}

//------------------------------------------------------
// VRComfortVignette
//	how strongly to vignette this frame (vr_comfortVignette): artificial
//	motion only, the player's speed and the turning the head did not do (the
//	rate of the tracking yaw). A change of more than 15 degrees in a frame is
//	a snap turn or a recentre, a cut rather than motion. While game time
//	stands still (paused, g_stopTime) the speed the player stopped at would
//	hold the edges dark, so only turning counts.
//------------------------------------------------------
float hhPlayerView::VRComfortVignette( float trackingYaw ) {
	const float setting = idMath::ClampFloat( 0.0f, 1.0f, cvarSystem->GetCVarFloat( "vr_comfortVignette" ) );
	const int now = sys->Milliseconds();
	const float seconds = vrComfortTime > 0 ? idMath::ClampFloat( 0.0f, 0.25f, ( now - vrComfortTime ) * 0.001f ) : 0.0f;
	float turnRate = 0.0f;
	if ( seconds > 0.0f ) {
		const float delta = idMath::AngleNormalize180( trackingYaw - vrComfortYaw );
		if ( idMath::Fabs( delta ) < 15.0f ) {
			turnRate = delta / seconds;
		}
	}
	const bool gameMoved = gameLocal.time != vrComfortGameTime;
	vrComfortYaw = trackingYaw;
	vrComfortTime = now;
	vrComfortGameTime = gameLocal.time;
	const float speed = gameMoved ? player->GetPhysics()->GetLinearVelocity().Length() : 0.0f;
	const float target = setting > 0.0f ? VR_ComfortMotion( speed, turnRate ) : 0.0f;
	vrComfort = VR_ComfortEase( vrComfort, target, seconds );
	return vrComfort * setting;
}

//------------------------------------------------------
// GetVRAimMarker
//	where the weapon hand's shot lands (vr_aimLaser), while the controller
//	aims: the path the gun in the hand fires along (hhPlayer::GetVRHandAim),
//	from this draw's pose. A beam (vr_aimLaser 2) leaves the drawn gun's
//	muzzle, or the hand without one. The marker stands in for the crosshair
//	on the virtual screen, which would hang at the HUD's depth off the line
//	of fire; it marks nothing while the crosshair would be away (the GUI hand
//	up, a world GUI in focus, no weapon).
//------------------------------------------------------
bool hhPlayerView::GetVRAimMarker( const vrFrameState_t &frame, const idVec3 &headOrigin, bool weaponHeld,
		const idVec3 &weaponOrigin, const idMat3 &weaponAxis, vrAimMarker_t &marker ) {
	hhPlayer *hhplayer = static_cast<hhPlayer *>( player );
	if ( frame.aimMode != VR_AIM_HAND || frame.aimLaser == VR_AIM_LASER_OFF || player->health <= 0 || player->spectating ) {
		return false;
	}
	if ( !hhplayer->CrosshairWanted() ) {
		return false;
	}
	idVec3 start;
	idMat3 aimAxis;
	if ( !hhplayer->GetVRHandAim( start, aimAxis ) ) {
		return false;
	}

	trace_t trace;
	gameLocal.clip.TracePoint( trace, start, start + aimAxis[0] * VR_AIM_RANGE, MASK_SHOT_RENDERMODEL, player );
	if ( !weaponHeld || !hhplayer->weapon.IsValid() || !hhplayer->weapon->GetVRMuzzle( weaponOrigin, weaponAxis, marker.muzzle ) ) {
		marker.muzzle = start;
	}
	marker.target = trace.endpos;
	marker.hit = trace.fraction < 1.0f;

	// round a corner the hand can see what the head can't
	marker.hidden = false;
	const idVec3 toTarget = marker.target - headOrigin;
	const float distance = toTarget.Length();
	if ( frame.head.valid && distance > 8.0f ) {
		trace_t sight;
		gameLocal.clip.TracePoint( sight, headOrigin, marker.target - toTarget * ( 4.0f / distance ), MASK_SHOT_RENDERMODEL, player );
		marker.hidden = sight.fraction < 1.0f;
	}
	return true;
}

//------------------------------------------------------
// VRView
//	The world once per eye, each from its tracked pose with its own off-axis
//	frustum. Overlays that tint the world (the view overlay, the low-health
//	tint, spirit walk's, fades) go into the eyes; screen blobs go to the
//	virtual screen with the HUD, which the caller draws next. Motion blur,
//	scratch-capture overlays, the sun corona's 2D flare and screen shake are
//	flat-screen effects and stand down. False when the frame has no eye to
//	render into: the caller then draws the flat view.
//------------------------------------------------------
bool hhPlayerView::VRView( idUserInterface *hud, const renderView_t *view, const vrFrameState_t &frame, float trackingYaw ) {
	if ( view == NULL || !renderSystem->SetVRRenderTarget( 0 ) ) {
		// tiled screenshots deliberately render to the desktop: the pose is
		// still valid, but no eye target belongs to this draw
		return false;
	}
	hhPlayer *hhplayer = static_cast<hhPlayer *>( player );

	// the tracking space: at the eye, in the player's gravity frame
	const idVec3 eyeOrigin = hhplayer->GetEyePosition();
	const idMat3 eyeAxis = hhplayer->GetEyeAxis();
	const idMat3 tracking = VR_TrackingAxis( trackingYaw ) * eyeAxis;
	const idVec3 correction = VR_HeadOffsetCorrection( frame );

	// the listener follows the tracked head, and the vignette centres on
	// where it looks, in both eyes
	idVec3 headOrigin = eyeOrigin;
	idMat3 headAxis = view->viewaxis;
	if ( frame.head.valid ) {
		headOrigin = eyeOrigin + ( frame.head.origin + correction ) * tracking;
		headAxis = frame.head.axis * tracking;
	}
	gameSoundWorld->PlaceListener( headOrigin, headAxis, player->entityNumber + 1, gameLocal.time, hud ? hud->State().GetString( "location" ) : "Undefined" );

	// the gun in the weapon hand, placed from this draw's pose: the hand
	// moves every headset frame, whether or not a game tic ran
	idVec3 weaponOrigin;
	idMat3 weaponAxis;
	const bool weaponHeld = hhplayer->GetVRWeaponTransform( weaponOrigin, weaponAxis );
	if ( weaponHeld ) {
		hhplayer->weapon->PresentVRHold( weaponOrigin, weaponAxis );
	}

	const idMaterial *whiteMaterial = declManager->FindMaterial( "_white" );
	vrAimMarker_t aimMarker;
	vrAimMarked = GetVRAimMarker( frame, headOrigin, weaponHeld, weaponOrigin, weaponAxis, aimMarker );
	const int aimLaser = frame.aimLaser;
	const float zoomScale = VRZoomScale();
	const float vignette = VRComfortVignette( trackingYaw );
	const bool viewEffects = !g_skipViewEffects.GetBool();
	if ( viewEffects ) {
		UpdateViewOverlays();
	}
	const bool spiritWalking = viewEffects && hhplayer->IsSpiritWalking();
	if ( spiritWalking && !spiritMaterial ) {
		spiritMaterial = declManager->FindMaterial( player->spawnArgs.GetString( "mtr_spiritwalk" ) );
	}

	if ( cvarSystem->GetCVarInteger( "vr_debug" ) >= 2 ) {
		// the head's up shows which way the gravity frame stands
		gameLocal.Printf( "VR drawn head %d (%s) up (%s) vignette %.3f\n", frame.frameNumber, headOrigin.ToString( 2 ), headAxis[2].ToString( 2 ), vignette );
		if ( weaponHeld ) {
			// the held gun in the head's own axes, and where a beam leaves it
			const idVec3 local = ( weaponOrigin - headOrigin ) * headAxis.Transpose();
			gameLocal.Printf( "VR held weapon %d (%s) head-relative (%s) muzzle (%s)\n", frame.frameNumber, weaponOrigin.ToString( 2 ),
				local.ToString( 2 ), vrAimMarked ? aimMarker.muzzle.ToString( 2 ) : "none" );
		}
	}

	for ( int eye = 0; eye < VR_NUM_EYES; eye++ ) {
		if ( eye > 0 && !renderSystem->SetVRRenderTarget( eye ) ) {
			break;
		}
		// the eye in tracking space, then carried into the gravity frame
		renderView_t eyeView = *view;
		VR_BuildEyeView( frame, eye, vec3_origin, trackingYaw, eyeView );
		eyeView.vieworg = eyeOrigin + eyeView.vieworg * eyeAxis;
		eyeView.viewaxis = eyeView.viewaxis * eyeAxis;
		// the eye as the lens shows it, whatever a weapon's zoom magnifies
		const renderView_t lensView = eyeView;
		if ( zoomScale < 1.0f ) {
			eyeView.fovTanLeft *= zoomScale;
			eyeView.fovTanRight *= zoomScale;
			eyeView.fovTanUp *= zoomScale;
			eyeView.fovTanDown *= zoomScale;
			eyeView.fov_x = RAD2DEG( 2.0f * idMath::ATan( idMath::Tan( DEG2RAD( eyeView.fov_x * 0.5f ) ) * zoomScale ) );
			eyeView.fov_y = RAD2DEG( 2.0f * idMath::ATan( idMath::Tan( DEG2RAD( eyeView.fov_y * 0.5f ) ) * zoomScale ) );
		}

		gameRenderWorld->RenderScene( &eyeView );

		if ( viewEffects && !player->spectating ) {
			DrawViewOverlays( false );
			if ( spiritWalking ) {
				renderSystem->SetColor4( 1, 1, 1, 1 );
				renderSystem->DrawStretchPic( 0, 0, 640, 480, 0, 1, 1, 0, spiritMaterial );
			}
		}
		VR_DrawComfortVignette( lensView, headAxis[0], vignette, vignette > 0.01f ? whiteMaterial : NULL );
		if ( vrAimMarked ) {
			VR_DrawAimMarker( eyeView, aimMarker, aimLaser, whiteMaterial );
		}
		if ( viewEffects ) {
			ScreenFade();
		}
	}
	renderSystem->SetVRRenderTarget( -1 );

	// the virtual screen, in front of the eyes: the screen blobs here, then
	// the HUD the caller draws
	if ( viewEffects && !player->spectating && !pm_thirdPerson.GetBool() ) {
		DrawScreenBlobs();
	}
	return true;
}

// Hermite()
// Hermite Interpolator
// Returns an alpha value [0..1] based on Hermite Parameters N1, N2, S1, S2 and an input alpha 't'
float Hermite(float t, float N1, float N2, float S1, float S2) {
	float tSquared = t*t;
	float tCubed = tSquared*t;
	return	(2*tCubed - 3*tSquared + 1)*N1 +
			(-2*tCubed + 3*tSquared)*N2 +
			(tCubed - 2*tSquared + t)*S1 +
			(tCubed - tSquared)*S2;
}

static void HH_GetMotionBlurCaptureSize( const renderView_t *view, int &captureWidth, int &captureHeight, bool &forceDimensions ) {
	captureWidth = SCREEN_WIDTH;
	captureHeight = SCREEN_HEIGHT;
	forceDimensions = false;

	// Retail PREY.exe requests a full-view scratch capture before damage blur.
	// Keep that by default and only downsample when explicitly requested.
	if ( !g_lowresFullscreenFX.GetBool() || view == NULL ) {
		return;
	}

	const int lowResMaxDimension = 512;
	const int viewWidth = Max( 1, view->width );
	const int viewHeight = Max( 1, view->height );
	const float aspect = static_cast<float>( viewWidth ) / static_cast<float>( viewHeight );

	if ( aspect >= 1.0f ) {
		captureWidth = lowResMaxDimension;
		captureHeight = Max( 1, idMath::FtoiFast( ( static_cast<float>( lowResMaxDimension ) / aspect ) + 0.5f ) );
	} else {
		captureHeight = lowResMaxDimension;
		captureWidth = Max( 1, idMath::FtoiFast( ( static_cast<float>( lowResMaxDimension ) * aspect ) + 0.5f ) );
	}

	forceDimensions = true;
}


//------------------------------------------------------
// MotionBlurVision
//	HUMANHEAD pdm
//------------------------------------------------------

void hhPlayerView::MotionBlurVision(idUserInterface *hud, const renderView_t *view) {
	if ( !g_doubleVision.GetBool() ) {
		SingleView( hud, view );
		return;
	}

	float alpha;
	const float N1 = 0.2f;
	const float N2 = 0.0f;
	const float S1 = 1.0f;
	const float S2 = 1.0f;

	float remainingTime = mbFinishTime - gameLocal.time;
	float elapsedTime = mbTotalTime - remainingTime;
	float scale = remainingTime / mbTotalTime;
	int captureWidth = SCREEN_WIDTH;
	int captureHeight = SCREEN_HEIGHT;
	bool forceCaptureDimensions = false;

	HH_GetMotionBlurCaptureSize( view, captureWidth, captureHeight, forceCaptureDimensions );

	// Render to a texture
	RENDER_DEMO_VIEWRENDER(view, this); //HUMANHEAD rww
	renderSystem->CropRenderSize( captureWidth, captureHeight, false, forceCaptureDimensions );
	SingleView( hud, view );
	renderSystem->CaptureRenderToImage( "_scratch" );
	renderSystem->UnCrop();
	RENDER_DEMO_VIEWRENDER_END(); //HUMANHEAD rww

	// Motion blur
	float xshift, yshift;
	for (int index=0; index<g_mbNumBlurs.GetInteger(); index++) {

		float curtime = elapsedTime - g_mbFrameSpan.GetFloat()*index*scale;
		float blurfactor = (index+1)/g_mbNumBlurs.GetFloat();

		// Hermite blend here (N1 is severity (0 - 0.5) )
		alpha = curtime/mbTotalTime;
		alpha = Hermite(alpha, N1, N2, S1, S2);	// Hermite parms: N1, N2, S1, S2
		
		xshift = blurfactor * scale * mbDirection.x * alpha * mbAmplitude;
		yshift = blurfactor * scale * mbDirection.y * alpha * mbAmplitude;

		#define CLIP(a) ((a)<0?0:(a)>1?1:(a))
		renderSystem->SetColor4( 1,1,1, index==0 ? 1.0f : 0.2f );
		renderSystem->DrawStretchPic( 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT,
			CLIP(xshift), CLIP(1+yshift), CLIP(1+xshift), CLIP(yshift), scratchMaterial ); // clipped
	}
}

//------------------------------------------------------
// SpiritVision
//	HUMANHEAD cjr
//------------------------------------------------------

void hhPlayerView::SpiritVision( idUserInterface *hud, const renderView_t *view ) {
	int oldTime = voTotalTime;
	const idMaterial *oldMaterial = viewOverlayMaterial;

	voTotalTime = -1;
	viewOverlayMaterial = NULL;

	SingleView( hud, view );

	// Draw the spiritwalk image over the top
	if ( player && !spiritMaterial ) {
		spiritMaterial = declManager->FindMaterial( player->spawnArgs.GetString( "mtr_spiritwalk" ) );
	}

	renderSystem->SetColor4( 1, 1, 1, 1 );
	renderSystem->DrawStretchPic(0, 0, 640, 480, 0, 1, 1, 0, spiritMaterial );

	voTotalTime = oldTime;
	viewOverlayMaterial = oldMaterial;
}

//------------------------------------------------------
// ApplyLetterbox
//	HUMANHEAD pdm
//------------------------------------------------------
void hhPlayerView::ApplyLetterBox(const renderView_t *view) {
	if (bLetterBox) {
		renderSystem->SetColor4( 1.0f, 1.0f, 1.0f, 1.0f );
		renderSystem->DrawStretchPic(0, 0, 640, LETTERBOX_HEIGHT_TOP, 0, 0, 1, 1, letterboxMaterial);
		renderSystem->DrawStretchPic(0, 480-LETTERBOX_HEIGHT_BOTTOM, 640, LETTERBOX_HEIGHT_BOTTOM, 0, 0, 1, 1, letterboxMaterial);
	}
}

//------------------------------------------------------
// MotionBlur
//	HUMANHEAD pdm
//------------------------------------------------------
void hhPlayerView::MotionBlur(int mbTime, float severity, idVec3 &direction) {
	mbTotalTime = mbTime;
	mbFinishTime = gameLocal.time + mbTotalTime;
	mbAmplitude = severity;
	mbDirection = direction;
}

//------------------------------------------------------
// SetLetterBox
//	HUMANHEAD pdm
//------------------------------------------------------
void hhPlayerView::SetLetterBox(bool on) {
	bLetterBox = on;
}

//------------------------------------------------------
// UpdateWeaponExamineFocus
//
// openPR06: the first time Tommy raises a weapon he turns it over in his hands
// (the weapon's initialPickup anim, weapon_base::NewRaise). Pull the focus
// onto the weapon while he does: the renderer blurs the world behind it and
// keeps the view weapon sharp (idRenderSystem::SetViewDepthOfField,
// r_depthOfField). Eased in game time, so a pause holds the focus where it is.
//------------------------------------------------------
void hhPlayerView::UpdateWeaponExamineFocus( void ) {
	const int now = gameLocal.time;
	if ( now < weaponExamineFocusTime ) {
		// a new map or a restored game restarted the clock
		weaponExamineFocus = 0.0f;
	}
	const float seconds = idMath::ClampFloat( 0.0f, 0.1f, MS2SEC( now - weaponExamineFocusTime ) );
	weaponExamineFocusTime = now;

	float target = 0.0f;
	const hhWeapon *weapon = player->weapon.GetEntity();
	if ( weapon != NULL && !weapon->IsHidden() && player->CanShowWeaponViewmodel()
			&& !player->spectating && !player->IsDead() && !gameLocal.inCinematic && !pm_thirdPerson.GetBool() ) {
		const int examineEnd = weapon->GetExamineEndTime();
		if ( examineEnd - SEC2MS( WEAPON_EXAMINE_FOCUS_OUT_SEC ) > now ) {
			target = 1.0f;
		}
	}

	if ( weaponExamineFocus < target ) {
		weaponExamineFocus = Min( target, weaponExamineFocus + seconds / WEAPON_EXAMINE_FOCUS_IN_SEC );
	} else if ( weaponExamineFocus > target ) {
		weaponExamineFocus = Max( target, weaponExamineFocus - seconds / WEAPON_EXAMINE_FOCUS_OUT_SEC );
	}

	// smoothstep, so the pull starts and settles gently
	const float eased = weaponExamineFocus * weaponExamineFocus * ( 3.0f - 2.0f * weaponExamineFocus );
	const float radius = r_depthOfFieldRadius.GetFloat();
	renderViewDepthOfField_t dof;
	if ( eased > 0.0f && radius > 0.0f ) {
		// The renderer's thin lens blurs a pixel at distance d by
		// K * ( 1 - S / d ), S the focus distance, with
		// K = f^2 / ( N * ( S - f ) ) / 36 mm * viewWidth (all in mm). Pick N
		// so K is radius at the view's height (radius is in 1080-line pixels):
		// the far scene is almost fully soft, nearer surfaces less so.
		const float width = static_cast<float>( Max( 1, renderSystem->GetScreenWidth() ) );
		const float height = static_cast<float>( Max( 1, renderSystem->GetScreenHeight() ) );
		const float f = WEAPON_EXAMINE_FOCAL_LENGTH_MM;
		const float focusMm = WEAPON_EXAMINE_FOCUS_DISTANCE * 25.4f;
		const float k = radius * height / 1080.0f;
		dof.amount = eased;
		dof.flags = VIEW_DOF_SHARP_VIEW_WEAPON;
		dof.focusDistance = WEAPON_EXAMINE_FOCUS_DISTANCE;
		dof.focalLength = f;
		dof.fStop = f * f * width / ( ( focusMm - f ) * 36.0f * k );
		dof.maxBlur = radius;
	}

	// openPR06: an open weapon wheel wins: the view weapon and the world near
	// it stay sharp and the rest goes out of focus behind the ring
	// (game_weaponwheel.cpp). The player's Depth of Field setting gates it in
	// the renderer, as it does the examine focus.
	const float wheel = static_cast<hhPlayer *>( player )->GetWeaponWheelBlend();
	if ( wheel > 0.0f && !player->spectating && !pm_thirdPerson.GetBool() ) {
		dof = renderViewDepthOfField_t();
		dof.amount = wheel * wheel * ( 3.0f - 2.0f * wheel );
		dof.flags = VIEW_DOF_FOCUS_VIEW_WEAPON;
	}
	renderSystem->SetViewDepthOfField( dof );
}

//------------------------------------------------------
// RenderPlayerView
//------------------------------------------------------
void hhPlayerView::RenderPlayerView( idUserInterface *hud ) {
	const renderView_t *view = player->GetRenderView();
	const bool previousUseUIViewportFor2D = renderSystem->GetUseUIViewportFor2D();

	// before any RenderScene below: the renderer latches it onto each view
	UpdateWeaponExamineFocus();

	// Retail PREY.exe emits view damage/effect overlays as fullscreen 2D passes,
	// not HUD quads constrained to the UI viewport safe-area.
	renderSystem->SetUseUIViewportFor2D( false );

	// openPR06 VR: the eyes take the first-person view while a headset presents
	vrFrameState_t vrFrame;
	float vrTrackingYaw = 0.0f;
	vrAimMarked = false;
	if ( GetVRView( vrFrame, vrTrackingYaw ) && VRView( hud, view, vrFrame, vrTrackingYaw ) ) {
		if ( !g_skipViewEffects.GetBool() ) {
			ApplyLetterBox( view );
		}
	} else if ( g_skipViewEffects.GetBool() ) {
		SingleView( hud, view );
	} else {
		if (gameLocal.time < mbFinishTime) {
			MotionBlurVision(hud, view);
		} else if ( ((hhPlayer *)player)->IsSpiritWalking() ) {
			SpiritVision( hud, view );
		} else {
			SingleView(hud, view);
		}
		ScreenFade();

		// HUMANHEAD pdm: letterbox
		ApplyLetterBox(view);
	}

	renderSystem->SetUseUIViewportFor2D( previousUseUIViewportFor2D );

	// HUMANHEAD: Draw the HUD after all over overlay effects.
	if (hud) {
		hud->SetStateBool("letterbox", bLetterBox);
		player->DrawHUD( hud );
	}

	// openPR06: the weapon wheel over everything, with or without the HUD
	static_cast<hhPlayer *>( player )->DrawWeaponWheel();

	if ( net_clientLagOMeter.GetBool() && lagoMaterial && gameLocal.isClient ) {
		renderSystem->SetColor4( 1.0f, 1.0f, 1.0f, 1.0f );
		renderSystem->DrawStretchPic( 10.0f, 380.0f, 64.0f, 64.0f, 0.0f, 0.0f, 1.0f, 1.0f, lagoMaterial );
	}	
}
