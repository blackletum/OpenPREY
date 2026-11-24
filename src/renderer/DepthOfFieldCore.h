// Copyright (C) 2026 DarkMatter Productions
//
// Backend-neutral policy for the openPR06 depth of field post-process
// (idRenderSystem::SetDepthOfFieldView). OpenGL (draw_common.cpp,
// glprogs/depthoffield.fs) and Vulkan (vk_PostProcess.cpp,
// post_depthoffield.frag) keep their own GPU work; both size the blur through
// these functions so the backends cannot drift apart.
//
// The shaders compute each pixel's circle of confusion from its linear view
// distance d and the focus distance f as radius * clamp( ( d - f ) / d, 0, 1 ),
// the thin-lens falloff of a lens focused close: the far scene is almost
// fully soft, nearer surfaces less so. Depth at or below
// DEPTH_OF_FIELD_WEAPON_DEPTH is the view weapon's depth-hacked range (both
// backends draw weaponDepthHack surfaces into window depth [0, 0.5]), which
// is always in focus, so the weapon and Tommy's hands stay sharp.

#ifndef __DEPTH_OF_FIELD_CORE_H__
#define __DEPTH_OF_FIELD_CORE_H__

static const float DEPTH_OF_FIELD_WEAPON_DEPTH = 0.5f;
// r_depthOfFieldRadius is authored for a view this many lines tall.
static const float DEPTH_OF_FIELD_REFERENCE_HEIGHT = 1080.0f;
// Below this radius the pass would change no pixel visibly; skip it.
static const float DEPTH_OF_FIELD_MIN_RADIUS_PIXELS = 0.5f;
// Matches the r_depthOfFieldRadius cvar range.
static const float DEPTH_OF_FIELD_MAX_RADIUS_PIXELS = 32.0f;

// The largest blur radius for this view, in pixels: the published amount
// pulls the focus in by growing the radius, rather than cross-fading.
inline float DepthOfFieldCore_RadiusPixels( float amount, float radiusSetting, int viewportHeight ) {
	if ( amount <= 0.0f || radiusSetting <= 0.0f || viewportHeight <= 0 ) {
		return 0.0f;
	}
	if ( amount > 1.0f ) {
		amount = 1.0f;
	}
	if ( radiusSetting > DEPTH_OF_FIELD_MAX_RADIUS_PIXELS ) {
		radiusSetting = DEPTH_OF_FIELD_MAX_RADIUS_PIXELS;
	}
	// scale with the view, so the look holds at any resolution, but never
	// past what the shader's fixed tap count covers without visible gaps
	float radius = amount * radiusSetting * ( (float)viewportHeight / DEPTH_OF_FIELD_REFERENCE_HEIGHT );
	const float maxRadius = DEPTH_OF_FIELD_MAX_RADIUS_PIXELS * 2.0f;
	return radius > maxRadius ? maxRadius : radius;
}

inline bool DepthOfFieldCore_Visible( float radiusPixels ) {
	return radiusPixels >= DEPTH_OF_FIELD_MIN_RADIUS_PIXELS;
}

#endif // __DEPTH_OF_FIELD_CORE_H__
