#version 450

// openPR06 depth of field. A port of content/basepr/pak0/glprogs/depthoffield.fs
// (RB_STD_DepthOfField); see that file and src/renderer/DepthOfFieldCore.h for
// the focus model and the gather. The body is that file with its uniforms in a
// block. fragUV is OpenGL's texture coordinate; see post_ssao.frag. The
// captures are exactly the view's size.

layout(set = 0, binding = 0) uniform sampler2D Scene;
layout(set = 1, binding = 0) uniform sampler2D DepthBuffer;

layout(std140, set = 6, binding = 0) uniform DepthOfFieldBlock {
    vec4 texInfo;		// xy: invTexSize, zw: the view's last texel centre
    vec4 dofParams;		// x: radius in pixels, y: focus distance, zw: depthProjection ( P[10], P[14] )
} block;

layout(location = 0) in vec2 fragUV;
layout(location = 0) out vec4 outColor;

const int kTaps = 40;
const float kGoldenAngle = 2.39996323;
const float kWeaponDepth = 0.5;

float ViewDistance( float depth ) {
	float ndcDepth = depth * 2.0 - 1.0;
	float denom = ndcDepth + block.dofParams.z;
	if ( abs( denom ) < 0.00001 ) {
		denom = ( denom < 0.0 ) ? -0.00001 : 0.00001;
	}
	return abs( block.dofParams.w / denom );
}

float CircleOfConfusion( float depth ) {
	if ( depth <= kWeaponDepth ) {
		return 0.0;
	}
	float d = max( ViewDistance( depth ), 0.001 );
	return block.dofParams.x * clamp( ( d - block.dofParams.y ) / d, 0.0, 1.0 );
}

void main() {
	vec2 uv = fragUV;
	vec4 center = texture( Scene, uv );
	float centerDepth = texture( DepthBuffer, uv ).x;
	float centerCoC = CircleOfConfusion( centerDepth );
	if ( centerCoC < 0.5 ) {
		outColor = center;
		return;
	}

	vec4 sum = center;
	float weightSum = 1.0;
	for ( int i = 0; i < kTaps; ++i ) {
		float t = ( float( i ) + 0.5 ) / float( kTaps );
		float r = sqrt( t ) * centerCoC;
		float a = float( i ) * kGoldenAngle;
		vec2 sampleUV = clamp( uv + vec2( cos( a ), sin( a ) ) * r * block.texInfo.xy, vec2( 0.0 ), block.texInfo.zw );
		float sampleDepth = texture( DepthBuffer, sampleUV ).x;
		float sampleCoC = CircleOfConfusion( sampleDepth );
		if ( sampleDepth > centerDepth ) {
			sampleCoC = min( sampleCoC, centerCoC );
		}
		float w = clamp( sampleCoC - r + 1.0, 0.0, 1.0 );
		sum += texture( Scene, sampleUV ) * w;
		weightSum += w;
	}
	outColor = sum / weightSum;
}
