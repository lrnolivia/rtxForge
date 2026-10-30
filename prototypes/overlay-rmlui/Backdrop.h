#pragma once
#include <d3d11.h>
#include <d3dcompiler.h>
#include <wrl/client.h>
#include <vector>
#include <algorithm>
#include <cstring>
#include <stdexcept>
#include <array>

// The game-facing boundary: copy the existing scene, blur it at quarter
// resolution, and composite only the rounded panel regions. UI glyphs never
// enter this pass. HDR scenes are decoded only for the glass working surface;
// the final composition blends in linear light and preserves untouched pixels.
class Backdrop
{
    template<class T>using Ptr=Microsoft::WRL::ComPtr<T>;
    Ptr<ID3D11Device> device;
    Ptr<ID3D11DeviceContext> context;
    Ptr<ID3D11VertexShader> vertex;
    Ptr<ID3D11PixelShader> copy,blur,glass,shadow,average,downsample,thumbnail,material,layer;
    Ptr<ID3D11Buffer> constants;
    Ptr<ID3D11SamplerState> sampler;
    Ptr<ID3D11BlendState> opaque,alpha;
    Ptr<ID3D11RasterizerState> raster;
    Ptr<ID3D11DepthStencilState> depth;
    Ptr<ID3D11Texture2D> scene,horizontal,vertical,reduced,surfaceTexture;
    Ptr<ID3D11ShaderResourceView> photo,sceneView,horizontalView,verticalView,reducedView,surfaceView;
    Ptr<ID3D11RenderTargetView> horizontalTarget,verticalTarget,reducedTarget,surfaceTarget;
    Ptr<ID3D11Texture2D> averageTexture;
    Ptr<ID3D11RenderTargetView> averageTarget;
    std::array<Ptr<ID3D11Texture2D>,4> readbacks;
    std::array<bool,4> pending{};
    Ptr<ID3D11Texture2D> gridTexture,gridReadback;
    Ptr<ID3D11RenderTargetView> gridTarget;
    bool gridPending=false;
    int width,height,qwidth,qheight;
    struct alignas(16) Data { float axis[2],screen[2],bounds[4],radius,saturation,grain,luminosity,uv[4],shadowColor[4],shadowParams[4],surface[4],pointer[4],output[4]; };
    Data data{};
    double lastSample=-1;
    static void Check(HRESULT n) { if(FAILED(n))throw std::runtime_error("Backdrop GPU setup failed"); }
    static Ptr<ID3DBlob> Compile(const char* source,const char* entry,const char* target)
    {
        Ptr<ID3DBlob> result,errors;
        const auto hr=D3DCompile(source,std::strlen(source),nullptr,nullptr,nullptr,entry,target,D3DCOMPILE_OPTIMIZATION_LEVEL3,0,&result,&errors);
        if(FAILED(hr))throw std::runtime_error(errors ? static_cast<const char*>(errors->GetBufferPointer()):"Backdrop shader compilation failed");
        return result;
    }
    void Upload()
    {
        D3D11_MAPPED_SUBRESOURCE mapped{};Check(context->Map(constants.Get(),0,D3D11_MAP_WRITE_DISCARD,0,&mapped));
        std::memcpy(mapped.pData,&data,sizeof(data));context->Unmap(constants.Get(),0);
    }
    void Bind(ID3D11RenderTargetView* target,ID3D11ShaderResourceView* source,ID3D11PixelShader* shader,int w,int h)
    {
        ID3D11ShaderResourceView* none=nullptr;context->PSSetShaderResources(0,1,&none);
        context->OMSetRenderTargets(1,&target,nullptr);
        D3D11_VIEWPORT viewport{0,0,float(w),float(h),0,1};context->RSSetViewports(1,&viewport);
        context->PSSetShaderResources(0,1,&source);context->PSSetShader(shader,nullptr,0);
        Upload();context->Draw(3,0);
    }
public:
    struct Panel { float x,y,width,height,radius,saturation{.65f},grain{.018f},luminosity{.04f},shadowOpacity{.18f},shadowRadius{28.f},shadowOffset{12.f},shadowBlend{},tone{.96f},grounding{.52f},blendAmount{.3f},blendMode{2},arrow{},anchorX{},opacity{1},scale{1},blur{32};size_t sampleIndex{}; };
    struct SceneColor {float r{},g{},b{};bool valid{};};
    std::array<SceneColor,64*36> grid;
    SceneColor Background(float x,float y,float w,float h) const {SceneColor c{};int count=0;for(int j=0;j<2;j++)for(int i=0;i<3;i++){const int gx=std::clamp(int((x+w*(i+.5f)/3)/width*64),0,63),gy=std::clamp(int((y+h*(j+.5f)/2)/height*36),0,35);const auto p=grid[gy*64+gx];if(p.valid){c.r+=p.r;c.g+=p.g;c.b+=p.b;++count;}}if(count){c.r/=count;c.g/=count;c.b/=count;c.valid=true;}return c;}
    std::array<SceneColor,4> measured;
    Backdrop(ID3D11Device* d,int w,int h,const unsigned char* image,int imageWidth,int imageHeight,const float uv[4],DXGI_FORMAT sceneFormat=DXGI_FORMAT_R8G8B8A8_UNORM,unsigned colorSpace=0):device(d),width(w),height(h),qwidth((w+3)/4),qheight((h+3)/4)
    {
        d->GetImmediateContext(&context);data.output[0]=float(colorSpace);data.output[1]=203.f;std::copy(uv,uv+4,data.uv);data.screen[0]=float(w);data.screen[1]=float(h);
        const char* shader=R"(
cbuffer Data : register(b0) {float2 axis;float2 screen;float4 bounds;float radius;float saturation;float grain;float luminosity;float4 crop;float4 shadowColor;float4 shadowParams;float4 surface;float4 pointer;float4 output;};
Texture2D image:register(t0);Texture2D blurredBackdrop:register(t1);SamplerState linearClamp:register(s0);
struct Vertex {float4 position:SV_Position;float2 uv:TEXCOORD;};
Vertex VS(uint id:SV_VertexID) {Vertex o;o.uv=float2((id<<1)&2,id&2);o.position=float4(o.uv.x*2-1,1-o.uv.y*2,0,1);return o;}
float4 Copy(Vertex v):SV_Target {return image.Sample(linearClamp,crop.xy+v.uv*crop.zw);}
// HDR10 is PQ/Rec.2020, while scRGB is linear Rec.709 with 80 nits per unit.
float3 SrgbDecode(float3 c){return lerp(c/12.92,pow(max((c+.055)/1.055,0),2.4),step(.04045,c));}
float3 SrgbEncode(float3 c){c=max(c,0);return lerp(c*12.92,1.055*pow(c,1/2.4)-.055,step(.0031308,c));}
float3 PqDecode(float3 c){float3 p=pow(saturate(c),1/(2523.0/32));return 10000*pow(max(p-3424.0/4096,0)/max(2413.0/128-2392.0/128*p,.000001),1/(2610.0/16384));}
float3 PqEncode(float3 n){float3 p=pow(saturate(n/10000),2610.0/16384);return pow((3424.0/4096+2413.0/128*p)/(1+2392.0/128*p),2523.0/32);}
float3 To709(float3 c){return mul(float3x3(1.660491,-.587641,-.072850,-.124550,1.132900,-.008349,-.018151,-.100579,1.118730),c);}
float3 To2020(float3 c){return mul(float3x3(.627404,.329283,.043313,.069097,.919540,.011362,.016391,.088013,.895595),c);}
float3 SceneLinear(float3 c){return output.x>1.5?To709(PqDecode(c)):c*80;}
float3 SceneWorking(float3 c){return output.x>.5?SrgbEncode(saturate(SceneLinear(c)/output.y)):c;}
float4 Downsample(Vertex v):SV_Target {float4 c=0;[unroll]for(int y=0;y<4;y++)[unroll]for(int x=0;x<4;x++)c+=image.Sample(linearClamp,v.uv+(float2(x,y)-1.5)/screen);return c/16;}
float4 Thumbnail(Vertex v):SV_Target {float4 c=0;[unroll]for(int y=0;y<4;y++)[unroll]for(int x=0;x<4;x++)c+=float4(SceneWorking(image.Sample(linearClamp,v.uv+(float2(x,y)/4-.375)*float2(1./64,1./36)).rgb),1);return c/16;}
float4 Layer(Vertex v):SV_Target {float4 c=0;[unroll]for(int i=0;i<8;i++)c+=image.Sample(linearClamp,v.uv+axis*(i/7.0))*(8-i);c/=36;if(output.x<.5)return c;
 // RGB in the UI layer is premultiplied sRGB. Decode after unpremultiplying,
 // blend in absolute linear light, then encode back to the game's transfer.
 if(c.a<=.00001)discard;
 float4 scene=blurredBackdrop.Sample(linearClamp,v.uv);
 float3 nits=lerp(SceneLinear(scene.rgb),SrgbDecode(saturate(c.rgb/c.a))*output.y,saturate(c.a));
 return float4(output.x>1.5?PqEncode(To2020(nits)):nits/80,scene.a);}
float4 Blur(Vertex v):SV_Target {float4 c=0;float total=0;[loop]for(int i=-18;i<=18;i++){float weight=exp(-float(i*i)/(2*radius*radius));c+=image.Sample(linearClamp,v.uv+axis*i)*weight;total+=weight;}return c/total;}
float3 SoftLight(float3 dst,float3 src) {
 float3 D=lerp(((16*dst-12)*dst+4)*dst,sqrt(max(dst,0)),step(.25,dst));
 return lerp(dst-(1-2*src)*dst*(1-dst),dst+(2*src-1)*(D-dst),step(.5,src));
}
float3 Overlay(float3 dst,float3 src) {return lerp(2*src*dst,1-2*(1-src)*(1-dst),step(.5,dst));}
float BlendLuma(float3 c){return dot(c,float3(.3,.59,.11));}
float3 SetLuma(float3 c,float l){c+=l-BlendLuma(c);float n=min(c.r,min(c.g,c.b)),x=max(c.r,max(c.g,c.b));if(n<0)c=l+(c-l)*l/max(l-n,.00001);if(x>1)c=l+(c-l)*(1-l)/max(x-l,.00001);return saturate(c);}
float3 SurfaceBlend(float3 dst,float3 src,float mode){
 if(mode>10.5)return abs(dst-src);
 if(mode>9.5)return SetLuma(dst,BlendLuma(src));
 if(mode>8.5)return SetLuma(src,BlendLuma(dst));
 if(mode>7.5)return max(dst,src);
 if(mode>6.5)return min(dst,src);
 if(mode>5.5)return Overlay(src,dst);
 if(mode>4.5)return 1-(1-dst)*(1-src);
 if(mode>3.5)return dst*src;
 if(mode>1.5)return SoftLight(dst,src);
 if(mode>.5)return Overlay(dst,src);
 return src;
}
float ShapeDistance(float2 position) {
 float2 halfSize=(bounds.zw-bounds.xy)*.5;float2 local=position-(bounds.xy+bounds.zw)*.5;
 float2 q=abs(local)-halfSize+radius;float d=length(max(q,0))+min(max(q.x,q.y),0)-radius;
 if(pointer.x>.5) {float scale=pointer.w;float y=position.y-(bounds.w-2*scale);float pointerDistance=max(abs(position.x-pointer.y)-10*scale+y*10/14,max(-y,y-14*scale));d=min(d,pointerDistance);}
 return d;
}
float4 Material(Vertex v):SV_Target {
 float3 destination=SceneWorking(image.Sample(linearClamp,v.uv).rgb);float3 color=destination;
 float luma=dot(color,float3(.2126,.7152,.0722));color=lerp(luma.xxx,color,saturation);
 color=lerp(color,((luma+.5)*.5).xxx,luminosity);color=lerp(color,surface.xxx,surface.y);
 return float4(lerp(color,SurfaceBlend(destination,color,surface.w),surface.z),1);
}
float4 Glass(Vertex v):SV_Target {
 float2 halfSize=(bounds.zw-bounds.xy)*.5;float2 local=v.position.xy-(bounds.xy+bounds.zw)*.5;
 float distance=ShapeDistance(v.position.xy);
 float aa=max(fwidth(distance),1);float mask=1-smoothstep(-aa*.6,aa*.6,distance);float3 color=image.Sample(linearClamp,v.uv).rgb;
 // A feathered inner optical rim, composed once with the rounded mask.
 float rim=(1-smoothstep(.25,1.8,-distance));
 float rimTone=lerp(.22,.95,saturate(.5-local.y/max(halfSize.y,1)));
 color=lerp(color,SoftLight(color,rimTone.xxx),rim*.55);
 float noise=frac(sin(dot(floor(v.position.xy),float2(12.9898,78.233)))*43758.5453)-.5;
 color=saturate(color+noise*grain);
 mask*=pointer.z;return float4(color*mask,mask);
}
float4 Shadow(Vertex v):SV_Target {
 float distance=ShapeDistance(v.position.xy-float2(0,shadowParams.z));
 // Broad local scene average avoids flickering on small bright details. The
 // continuous curve keeps existing depth in shadow and reduces it over light.
 float3 local=0;[unroll]for(int y=-1;y<=1;y++)[unroll]for(int x=-1;x<=1;x++)local+=SceneWorking(image.Sample(linearClamp,v.uv+float2(x,y)*12/screen).rgb);
 local/=9;float light=smoothstep(.22,.80,dot(local,float3(.2126,.7152,.0722)));
 float sigma=max(shadowParams.y,1)*lerp(1,1.25,light);float a=exp(-max(distance,0)*max(distance,0)/(2*sigma*sigma))*shadowParams.x*lerp(1,.30,light);
 float3 dst=SceneWorking(image.Sample(linearClamp,v.uv).rgb);float3 src=shadowColor.rgb;float3 blended=src;
 if(shadowParams.w>1.5) {
   float3 D=lerp(((16*dst-12)*dst+4)*dst,sqrt(max(dst,0)),step(.25,dst));
   blended=lerp(dst-(1-2*src)*dst*(1-dst),dst+(2*src-1)*(D-dst),step(.5,src));
 } else if(shadowParams.w>.5) blended=lerp(2*src*dst,1-2*(1-src)*(1-dst),step(.5,dst));
 a*=pointer.z;return float4(saturate(blended)*a,a);
}
float4 Average(Vertex v):SV_Target {float3 color=0;[unroll]for(int y=0;y<4;y++)[unroll]for(int x=0;x<4;x++)color+=SceneWorking(image.Sample(linearClamp,(bounds.xy+(float2(x,y)+.5)/4*(bounds.zw-bounds.xy))/screen).rgb);return float4(color/16,1);
})";
        auto vs=Compile(shader,"VS","vs_5_0");Check(d->CreateVertexShader(vs->GetBufferPointer(),vs->GetBufferSize(),nullptr,&vertex));
        auto make=[&](const char* entry,Ptr<ID3D11PixelShader>& result){auto code=Compile(shader,entry,"ps_5_0");Check(d->CreatePixelShader(code->GetBufferPointer(),code->GetBufferSize(),nullptr,&result));};
        make("Copy",copy);make("Layer",layer);make("Material",material);make("Downsample",downsample);make("Thumbnail",thumbnail);make("Blur",blur);make("Glass",glass);make("Shadow",shadow);make("Average",average);
        D3D11_BUFFER_DESC buffer{};buffer.ByteWidth=sizeof(Data);buffer.Usage=D3D11_USAGE_DYNAMIC;buffer.BindFlags=D3D11_BIND_CONSTANT_BUFFER;buffer.CPUAccessFlags=D3D11_CPU_ACCESS_WRITE;Check(d->CreateBuffer(&buffer,nullptr,&constants));
        D3D11_SAMPLER_DESC sample{};sample.Filter=D3D11_FILTER_MIN_MAG_MIP_LINEAR;sample.AddressU=sample.AddressV=sample.AddressW=D3D11_TEXTURE_ADDRESS_CLAMP;sample.MaxLOD=D3D11_FLOAT32_MAX;Check(d->CreateSamplerState(&sample,&sampler));
        D3D11_BLEND_DESC blend{};blend.RenderTarget[0].RenderTargetWriteMask=D3D11_COLOR_WRITE_ENABLE_ALL;Check(d->CreateBlendState(&blend,&opaque));
        auto& b=blend.RenderTarget[0];b.BlendEnable=TRUE;b.SrcBlend=D3D11_BLEND_ONE;b.DestBlend=D3D11_BLEND_INV_SRC_ALPHA;b.BlendOp=D3D11_BLEND_OP_ADD;b.SrcBlendAlpha=D3D11_BLEND_ONE;b.DestBlendAlpha=D3D11_BLEND_INV_SRC_ALPHA;b.BlendOpAlpha=D3D11_BLEND_OP_ADD;Check(d->CreateBlendState(&blend,&alpha));
        D3D11_RASTERIZER_DESC rs{};rs.FillMode=D3D11_FILL_SOLID;rs.CullMode=D3D11_CULL_NONE;rs.DepthClipEnable=TRUE;Check(d->CreateRasterizerState(&rs,&raster));
        D3D11_DEPTH_STENCIL_DESC ds{};ds.DepthEnable=FALSE;ds.StencilEnable=FALSE;Check(d->CreateDepthStencilState(&ds,&depth));
        const auto texture=[&](int tw,int th,UINT bind,const unsigned char* pixels,Ptr<ID3D11Texture2D>& tex,Ptr<ID3D11ShaderResourceView>& srv,Ptr<ID3D11RenderTargetView>* rtv) {
            D3D11_TEXTURE2D_DESC desc{};desc.Width=tw;desc.Height=th;desc.MipLevels=1;desc.ArraySize=1;desc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;desc.SampleDesc.Count=1;desc.BindFlags=bind;
            D3D11_SUBRESOURCE_DATA source{};source.pSysMem=pixels;source.SysMemPitch=tw*4;Check(d->CreateTexture2D(&desc,pixels?&source:nullptr,&tex));Check(d->CreateShaderResourceView(tex.Get(),nullptr,&srv));if(rtv)Check(d->CreateRenderTargetView(tex.Get(),nullptr,rtv->GetAddressOf()));
        };
        Ptr<ID3D11Texture2D> photoTexture;texture(imageWidth,imageHeight,D3D11_BIND_SHADER_RESOURCE,image,photoTexture,photo,nullptr);
        texture(w,h,D3D11_BIND_SHADER_RESOURCE,nullptr,scene,sceneView,nullptr);
        if(sceneFormat!=DXGI_FORMAT_R8G8B8A8_UNORM){D3D11_TEXTURE2D_DESC desc{};scene->GetDesc(&desc);desc.Format=sceneFormat;scene.Reset();sceneView.Reset();Check(d->CreateTexture2D(&desc,nullptr,&scene));Check(d->CreateShaderResourceView(scene.Get(),nullptr,&sceneView));}
        texture(w,h,D3D11_BIND_SHADER_RESOURCE|D3D11_BIND_RENDER_TARGET,nullptr,surfaceTexture,surfaceView,&surfaceTarget);
        texture(qwidth,qheight,D3D11_BIND_SHADER_RESOURCE|D3D11_BIND_RENDER_TARGET,nullptr,horizontal,horizontalView,&horizontalTarget);
        texture(qwidth,qheight,D3D11_BIND_SHADER_RESOURCE|D3D11_BIND_RENDER_TARGET,nullptr,vertical,verticalView,&verticalTarget);
        texture(qwidth,qheight,D3D11_BIND_SHADER_RESOURCE|D3D11_BIND_RENDER_TARGET,nullptr,reduced,reducedView,&reducedTarget);
        D3D11_TEXTURE2D_DESC avg{};avg.Width=avg.Height=avg.MipLevels=avg.ArraySize=1;avg.Format=DXGI_FORMAT_R8G8B8A8_UNORM;avg.SampleDesc.Count=1;avg.BindFlags=D3D11_BIND_RENDER_TARGET;
        Check(d->CreateTexture2D(&avg,nullptr,&averageTexture));Check(d->CreateRenderTargetView(averageTexture.Get(),nullptr,&averageTarget));
        avg.Usage=D3D11_USAGE_STAGING;avg.BindFlags=0;avg.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
        for(auto& readback:readbacks)Check(d->CreateTexture2D(&avg,nullptr,&readback));
        avg.Width=64;avg.Height=36;Check(d->CreateTexture2D(&avg,nullptr,&gridReadback));avg.Usage=D3D11_USAGE_DEFAULT;avg.CPUAccessFlags=0;avg.BindFlags=D3D11_BIND_RENDER_TARGET;Check(d->CreateTexture2D(&avg,nullptr,&gridTexture));Check(d->CreateRenderTargetView(gridTexture.Get(),nullptr,&gridTarget));
    }
    void Draw(ID3D11Texture2D* target,ID3D11RenderTargetView* rtv,const std::vector<Panel>& panels,bool enabled,bool redrawScene=true)
    {
        context->IASetInputLayout(nullptr);context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);context->VSSetShader(vertex.Get(),nullptr,0);context->GSSetShader(nullptr,nullptr,0);
        ID3D11ShaderResourceView* emptyResources[2]={};context->PSSetShaderResources(0,2,emptyResources);
        auto* cb=constants.Get();context->PSSetConstantBuffers(0,1,&cb);auto* sm=sampler.Get();context->PSSetSamplers(0,1,&sm);context->RSSetState(raster.Get());context->OMSetDepthStencilState(depth.Get(),0);context->OMSetBlendState(opaque.Get(),nullptr,0xffffffff);
        if(redrawScene)Bind(rtv,photo.Get(),copy.Get(),width,height);
        context->CopyResource(scene.Get(),target);
        for(const auto& panel:panels) {
            data.bounds[0]=panel.x;data.bounds[1]=panel.y;data.bounds[2]=panel.x+panel.width;data.bounds[3]=panel.y+panel.height;data.radius=panel.radius;
            data.saturation=panel.saturation;data.grain=panel.grain;data.luminosity=panel.luminosity;
            data.shadowColor[0]=data.shadowColor[1]=data.shadowColor[2]=.025f;
            data.surface[0]=panel.tone;data.surface[1]=panel.grounding;data.surface[2]=panel.blendAmount;data.surface[3]=panel.blendMode;
            data.pointer[0]=panel.arrow;data.pointer[1]=panel.anchorX;data.pointer[2]=panel.opacity;data.pointer[3]=panel.scale;
            data.shadowParams[0]=panel.shadowOpacity;data.shadowParams[1]=panel.shadowRadius;data.shadowParams[2]=panel.shadowOffset;data.shadowParams[3]=panel.shadowBlend;
            // Compose material first, then blur the combined result. Grain and
            // foreground UI are applied afterwards and stay crisp.
            context->OMSetBlendState(opaque.Get(),nullptr,0xffffffff);
            Bind(surfaceTarget.Get(),sceneView.Get(),material.Get(),width,height);
            if(enabled){Bind(reducedTarget.Get(),surfaceView.Get(),downsample.Get(),qwidth,qheight);data.radius=std::clamp(panel.blur/8.f,2.f,6.f);data.axis[0]=1.f/qwidth;data.axis[1]=0;Bind(horizontalTarget.Get(),reducedView.Get(),blur.Get(),qwidth,qheight);data.axis[0]=0;data.axis[1]=1.f/qheight;Bind(verticalTarget.Get(),horizontalView.Get(),blur.Get(),qwidth,qheight);data.radius=panel.radius;}
            context->OMSetBlendState(alpha.Get(),nullptr,0xffffffff);
            Bind(rtv,sceneView.Get(),shadow.Get(),width,height);
            Bind(rtv,enabled?verticalView.Get():surfaceView.Get(),glass.Get(),width,height);
        }
        context->PSSetShaderResources(0,2,emptyResources);
    }
    void SetPhoto(const unsigned char* pixels,int imageWidth,int imageHeight,const float uv[4]) {
        D3D11_TEXTURE2D_DESC desc{};desc.Width=imageWidth;desc.Height=imageHeight;desc.MipLevels=desc.ArraySize=1;desc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;desc.SampleDesc.Count=1;desc.BindFlags=D3D11_BIND_SHADER_RESOURCE;
        D3D11_SUBRESOURCE_DATA source{};source.pSysMem=pixels;source.SysMemPitch=imageWidth*4;Ptr<ID3D11Texture2D> texture;Check(device->CreateTexture2D(&desc,&source,&texture));Ptr<ID3D11ShaderResourceView> next;Check(device->CreateShaderResourceView(texture.Get(),nullptr,&next));photo=next;std::copy(uv,uv+4,data.uv);grid.fill({});measured={};pending={};gridPending=false;lastSample=-1;
    }
    void ComposeLayer(ID3D11RenderTargetView* destination,ID3D11ShaderResourceView* source,float vx,float vy,bool reducedMotion) {
        context->IASetInputLayout(nullptr);context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);context->VSSetShader(vertex.Get(),nullptr,0);context->GSSetShader(nullptr,nullptr,0);context->RSSetState(raster.Get());context->OMSetDepthStencilState(depth.Get(),0);context->OMSetBlendState(alpha.Get(),nullptr,0xffffffff);
        auto* cb=constants.Get();context->PSSetConstantBuffers(0,1,&cb);auto* sm=sampler.Get();context->PSSetSamplers(0,1,&sm);data.axis[0]=reducedMotion?0:std::clamp(vx/120.f,-12.f,12.f)/width;data.axis[1]=reducedMotion?0:std::clamp(vy/120.f,-12.f,12.f)/height;if(data.output[0]>.5f)context->OMSetBlendState(opaque.Get(),nullptr,0xffffffff);auto* background=sceneView.Get();context->PSSetShaderResources(1,1,&background);Bind(destination,source,layer.Get(),width,height);ID3D11ShaderResourceView* none[2]={};context->PSSetShaderResources(0,2,none);
    }
    void Sample(const std::vector<Panel>& panels,double now)
    {
        if(gridPending){D3D11_MAPPED_SUBRESOURCE map{};if(SUCCEEDED(context->Map(gridReadback.Get(),0,D3D11_MAP_READ,D3D11_MAP_FLAG_DO_NOT_WAIT,&map))){for(int y=0;y<36;y++)for(int x=0;x<64;x++){const auto* p=static_cast<const unsigned char*>(map.pData)+y*map.RowPitch+x*4;grid[y*64+x]={p[0]/255.f,p[1]/255.f,p[2]/255.f,true};}context->Unmap(gridReadback.Get(),0);gridPending=false;}}
        for(size_t i=0;i<readbacks.size();++i)if(pending[i]) {
            D3D11_MAPPED_SUBRESOURCE map{};const auto result=context->Map(readbacks[i].Get(),0,D3D11_MAP_READ,D3D11_MAP_FLAG_DO_NOT_WAIT,&map);
            if(SUCCEEDED(result)) {const auto* p=static_cast<const unsigned char*>(map.pData);measured[i]={p[0]/255.f,p[1]/255.f,p[2]/255.f,true};context->Unmap(readbacks[i].Get(),0);pending[i]=false;}
        }
        if(now-lastSample<.25)return;
        lastSample=now;context->OMSetBlendState(opaque.Get(),nullptr,0xffffffff);
        if(!gridPending){Bind(gridTarget.Get(),sceneView.Get(),thumbnail.Get(),64,36);context->CopyResource(gridReadback.Get(),gridTexture.Get());gridPending=true;}
        for(const auto& p:panels)if(p.sampleIndex<readbacks.size() && !pending[p.sampleIndex]) {
            const size_t i=p.sampleIndex;data.bounds[0]=p.x;data.bounds[1]=p.y;data.bounds[2]=p.x+p.width;data.bounds[3]=p.y+p.height;
            Bind(averageTarget.Get(),sceneView.Get(),average.Get(),1,1);context->CopyResource(readbacks[i].Get(),averageTexture.Get());pending[i]=true;
        }
        context->Flush();
    }
};
