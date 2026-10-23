#include "latency_imports.h"
#include <cstdio>
static bool missing{};
static FARPROC Resolve(HMODULE module,LPCSTR name){
  if(module!=(HMODULE)0x1234)return nullptr;
  if(reinterpret_cast<uintptr_t>(name)==7)return (FARPROC)0x7777;
  if(!strcmp(name,"NvLL_VK_NotifyOutOfBandQueue"))return missing?nullptr:(FARPROC)0x8888;
  return nullptr;
}
int main(int argc,char** argv){
  if(argc==3 || argc==4){
    auto legacy=argc==4?LoadLibraryExA(argv[3],nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_DEFAULT_DIRS):nullptr;
    auto legacyInitialize=legacy?GetProcAddress(legacy,"NvLL_VK_Initialize"):nullptr;
    if(argc==4 && (!legacy || !legacyInitialize || GetProcAddress(legacy,"NvLL_VK_NotifyOutOfBandQueue"))){puts("Expected legacy DLL with missing out-of-band export");return 1;}
    auto plugin=LoadLibraryExA(argv[1],nullptr,DONT_RESOLVE_DLL_REFERENCES);
    auto latency=LoadLibraryExA(argv[2],nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    if(!plugin || !latency){printf("DLL fixture load failed: %lu\n",GetLastError());return 1;}
    fgvk::LatencyBinding binding{};bool okay=fgvk::BindLatencyImports(plugin,latency,binding);
    if(legacy && (legacy==latency || GetProcAddress(legacy,"NvLL_VK_Initialize")!=legacyInitialize || GetProcAddress(legacy,"NvLL_VK_NotifyOutOfBandQueue"))){puts("Legacy module changed or private module not isolated");return 1;}
    printf("Real plugin latency binding: imports=%u status=%s\n",binding.imports,okay?"PASS":binding.error);
    if(legacy){puts("Legacy and private latency modules coexist; original exports unchanged: PASS");FreeLibrary(legacy);}
    FreeLibrary(plugin);FreeLibrary(latency);return okay && binding.imports?0:1;
  }
  auto image=(unsigned char*)VirtualAlloc(nullptr,4096,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
  if(!image)return 1;
  auto dos=(IMAGE_DOS_HEADER*)image;dos->e_magic=IMAGE_DOS_SIGNATURE;dos->e_lfanew=128;
  auto nt=(IMAGE_NT_HEADERS64*)(image+128);nt->Signature=IMAGE_NT_SIGNATURE;nt->OptionalHeader.Magic=IMAGE_NT_OPTIONAL_HDR64_MAGIC;nt->OptionalHeader.SizeOfImage=4096;
  nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT]={512,64};
  auto descriptor=(fgvk::DelayDescriptor*)(image+512);*descriptor={1,600,640,704,768,0,0,0};
  strcpy((char*)image+600,"NvLowLatencyVk.dll");
  auto names=(IMAGE_THUNK_DATA64*)(image+768);names[0].u1.AddressOfData=840;names[1].u1.Ordinal=IMAGE_ORDINAL_FLAG64|7;
  strcpy((char*)image+842,"NvLL_VK_NotifyOutOfBandQueue");
  auto iat=(IMAGE_THUNK_DATA64*)(image+704);iat[0].u1.Function=0x1111;iat[1].u1.Function=0x2222;
  int failed=0;auto check=[&](bool passed){if(!passed)++failed;};
  missing=true;fgvk::LatencyBinding refused{};
  check(!fgvk::BindLatencyImports((HMODULE)image,(HMODULE)0x1234,refused,Resolve));
  check(iat[0].u1.Function==0x1111 && iat[1].u1.Function==0x2222 && *(HMODULE*)(image+640)==nullptr);
  missing=false;fgvk::LatencyBinding bound{};
  check(fgvk::BindLatencyImports((HMODULE)image,(HMODULE)0x1234,bound,Resolve));
  check(bound.imports==2 && iat[0].u1.Function==0x8888 && iat[1].u1.Function==0x7777 && *(HMODULE*)(image+640)==(HMODULE)0x1234);
  descriptor->intable=4090;fgvk::LatencyBinding invalid{};
  check(!fgvk::BindLatencyImports((HMODULE)image,(HMODULE)0x1234,invalid,Resolve));
  VirtualFree(image,0,MEM_RELEASE);
  std::printf("5 latency import binding checks: %d failures\n",failed);return failed?1:0;
}
