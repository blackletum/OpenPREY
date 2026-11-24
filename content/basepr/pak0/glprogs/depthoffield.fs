// openPR06 depth of field (RB_STD_DepthOfField). The view weapon stays in
// focus while the world behind it goes soft, as when Tommy examines a newly
// acquired weapon. See src/renderer/DepthOfFieldCore.h for the focus model;
// Vulkan's post_depthoffield.frag is this file with its uniforms in a block.
//
// One gather pass: each pixel spreads its circle of confusion over a
// golden-angle disc of taps. A tap only counts where its own circle reaches
// back to this pixel, so the sharp weapon never smears into the blur behind
// it, and a farther tap may not blur wider than this pixel does.

uniform sampler2D Scene;
uniform sampler2D DepthBuffer;
uniform vec4 texInfo;		// xy: invTexSize, zw: the view's last texel centre in the scene texture
uniform vec4 dofParams;		// x: radius in pixels, y: focus distance, zw: depthProjection ( P[10], P[14] )

const int kTaps = 40;
const float kGoldenAngle = 2.39996323;
const float kWeaponDepth = 0.5;

float ViewDistance( float depth ) {
	float ndcDepth = depth * 2.0 - 1.0;
	float denom = ndcDepth + dofParams.z;
	if ( abs( denom ) < 0.00001 ) {
		denom = ( denom < 0.0 ) ? -0.00001 : 0.00001;
	}
	return abs( dofParams.w / denom );
}

float CircleOfConfusion( float depth ) {
	if ( depth <= kWeaponDepth ) {
		return 0.0;
	}
	float d = max( ViewDistance( depth ), 0.001 );
	return dofParams.x * clamp( ( d - dofParams.y ) / d, 0.0, 1.0 );
}

void main() {
	vec2 uv = gl_TexCoord[0].st;
	vec4 center = texture2D( Scene, uv );
	float centerDepth = texture2D( DepthBuffer, uv ).x;
	float centerCoC = CircleOfConfusion( centerDepth );
	if ( centerCoC < 0.5 ) {
		gl_FragColor = center;
		return;
	}

	vec4 sum = center;
	float weightSum = 1.0;
	for ( int i = 0; i < kTaps; ++i ) {
		float t = ( float( i ) + 0.5 ) / float( kTaps );
		float r = sqrt( t ) * centerCoC;
		float a = float( i ) * kGoldenAngle;
		vec2 sampleUV = clamp( uv + vec2( cos( a ), sin( a ) ) * r * texInfo.xy, vec2( 0.0 ), texInfo.zw );
		float sampleDepth = texture2D( DepthBuffer, sampleUV ).x;
		float sampleCoC = CircleOfConfusion( sampleDepth );
		if ( sampleDepth > centerDepth ) {
			sampleCoC = min( sampleCoC, centerCoC );
		}
		float w = clamp( sampleCoC - r + 1.0, 0.0, 1.0 );
		sum += texture2D( Scene, sampleUV ) * w;
		weightSum += w;
	}
	gl_FragColor = sum / weightSum;
}
