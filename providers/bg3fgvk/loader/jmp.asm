.code
extern ImportFuncTbl:QWORD
BinkAllocateFrameBuffers PROC
	jmp ImportFuncTbl[0 * 8]
BinkAllocateFrameBuffers ENDP
BinkClose PROC
	jmp ImportFuncTbl[1 * 8]
BinkClose ENDP
BinkCloseTrack PROC
	jmp ImportFuncTbl[2 * 8]
BinkCloseTrack ENDP
BinkControlBackgroundIO PROC
	jmp ImportFuncTbl[3 * 8]
BinkControlBackgroundIO ENDP
BinkCopyToBuffer PROC
	jmp ImportFuncTbl[4 * 8]
BinkCopyToBuffer ENDP
BinkCopyToBufferRect PROC
	jmp ImportFuncTbl[5 * 8]
BinkCopyToBufferRect ENDP
BinkCurrentSubtitle PROC
	jmp ImportFuncTbl[6 * 8]
BinkCurrentSubtitle ENDP
BinkDoFrame PROC
	jmp ImportFuncTbl[7 * 8]
BinkDoFrame ENDP
BinkDoFrameAsync PROC
	jmp ImportFuncTbl[8 * 8]
BinkDoFrameAsync ENDP
BinkDoFrameAsyncMulti PROC
	jmp ImportFuncTbl[9 * 8]
BinkDoFrameAsyncMulti ENDP
BinkDoFrameAsyncWait PROC
	jmp ImportFuncTbl[10 * 8]
BinkDoFrameAsyncWait ENDP
BinkDoFramePlane PROC
	jmp ImportFuncTbl[11 * 8]
BinkDoFramePlane ENDP
BinkFindXAudio2WinDevice PROC
	jmp ImportFuncTbl[12 * 8]
BinkFindXAudio2WinDevice ENDP
BinkFreeGlobals PROC
	jmp ImportFuncTbl[13 * 8]
BinkFreeGlobals ENDP
BinkGetError PROC
	jmp ImportFuncTbl[14 * 8]
BinkGetError ENDP
BinkGetFrameBuffersInfo PROC
	jmp ImportFuncTbl[15 * 8]
BinkGetFrameBuffersInfo ENDP
BinkGetGPUDataBuffersInfo PROC
	jmp ImportFuncTbl[16 * 8]
BinkGetGPUDataBuffersInfo ENDP
BinkGetKeyFrame PROC
	jmp ImportFuncTbl[17 * 8]
BinkGetKeyFrame ENDP
BinkGetPlatformInfo PROC
	jmp ImportFuncTbl[18 * 8]
BinkGetPlatformInfo ENDP
BinkGetRealtime PROC
	jmp ImportFuncTbl[19 * 8]
BinkGetRealtime ENDP
BinkGetRects PROC
	jmp ImportFuncTbl[20 * 8]
BinkGetRects ENDP
BinkGetSubtitleByIndex PROC
	jmp ImportFuncTbl[21 * 8]
BinkGetSubtitleByIndex ENDP
BinkGetSummary PROC
	jmp ImportFuncTbl[22 * 8]
BinkGetSummary ENDP
BinkGetTrackData PROC
	jmp ImportFuncTbl[23 * 8]
BinkGetTrackData ENDP
BinkGetTrackID PROC
	jmp ImportFuncTbl[24 * 8]
BinkGetTrackID ENDP
BinkGetTrackMaxSize PROC
	jmp ImportFuncTbl[25 * 8]
BinkGetTrackMaxSize ENDP
BinkGetTrackType PROC
	jmp ImportFuncTbl[26 * 8]
BinkGetTrackType ENDP
BinkGoto PROC
	jmp ImportFuncTbl[27 * 8]
BinkGoto ENDP
BinkLoadSubtitles PROC
	jmp ImportFuncTbl[28 * 8]
BinkLoadSubtitles ENDP
BinkLogoAddress PROC
	jmp ImportFuncTbl[29 * 8]
BinkLogoAddress ENDP
BinkNextFrame PROC
	jmp ImportFuncTbl[30 * 8]
BinkNextFrame ENDP
BinkOpen PROC
	jmp ImportFuncTbl[31 * 8]
BinkOpen ENDP
BinkOpenDirectSound PROC
	jmp ImportFuncTbl[32 * 8]
BinkOpenDirectSound ENDP
BinkOpenTrack PROC
	jmp ImportFuncTbl[33 * 8]
BinkOpenTrack ENDP
BinkOpenWaveOut PROC
	jmp ImportFuncTbl[34 * 8]
BinkOpenWaveOut ENDP
BinkOpenWithOptions PROC
	jmp ImportFuncTbl[35 * 8]
BinkOpenWithOptions ENDP
BinkOpenXAudio2 PROC
	jmp ImportFuncTbl[36 * 8]
BinkOpenXAudio2 ENDP
BinkOpenXAudio27 PROC
	jmp ImportFuncTbl[37 * 8]
BinkOpenXAudio27 ENDP
BinkOpenXAudio28 PROC
	jmp ImportFuncTbl[38 * 8]
BinkOpenXAudio28 ENDP
BinkOpenXAudio29 PROC
	jmp ImportFuncTbl[39 * 8]
BinkOpenXAudio29 ENDP
BinkPause PROC
	jmp ImportFuncTbl[40 * 8]
BinkPause ENDP
BinkRegisterFrameBuffers PROC
	jmp ImportFuncTbl[41 * 8]
BinkRegisterFrameBuffers ENDP
BinkRegisterGPUDataBuffers PROC
	jmp ImportFuncTbl[42 * 8]
BinkRegisterGPUDataBuffers ENDP
BinkRequestStopAsyncThread PROC
	jmp ImportFuncTbl[43 * 8]
BinkRequestStopAsyncThread ENDP
BinkRequestStopAsyncThreadsMulti PROC
	jmp ImportFuncTbl[44 * 8]
BinkRequestStopAsyncThreadsMulti ENDP
BinkService PROC
	jmp ImportFuncTbl[45 * 8]
BinkService ENDP
BinkSetError PROC
	jmp ImportFuncTbl[46 * 8]
BinkSetError ENDP
BinkSetFileOffset PROC
	jmp ImportFuncTbl[47 * 8]
BinkSetFileOffset ENDP
BinkSetFrameRate PROC
	jmp ImportFuncTbl[48 * 8]
BinkSetFrameRate ENDP
BinkSetIO PROC
	jmp ImportFuncTbl[49 * 8]
BinkSetIO ENDP
BinkSetIOSize PROC
	jmp ImportFuncTbl[50 * 8]
BinkSetIOSize ENDP
BinkSetMemory PROC
	jmp ImportFuncTbl[51 * 8]
BinkSetMemory ENDP
BinkSetOSFileCallbacks PROC
	jmp ImportFuncTbl[52 * 8]
BinkSetOSFileCallbacks ENDP
BinkSetPan PROC
	jmp ImportFuncTbl[53 * 8]
BinkSetPan ENDP
BinkSetSimulate PROC
	jmp ImportFuncTbl[54 * 8]
BinkSetSimulate ENDP
BinkSetSoundOnOff PROC
	jmp ImportFuncTbl[55 * 8]
BinkSetSoundOnOff ENDP
BinkSetSoundSystem PROC
	jmp ImportFuncTbl[56 * 8]
BinkSetSoundSystem ENDP
BinkSetSoundSystem2 PROC
	jmp ImportFuncTbl[57 * 8]
BinkSetSoundSystem2 ENDP
BinkSetSoundTrack PROC
	jmp ImportFuncTbl[58 * 8]
BinkSetSoundTrack ENDP
BinkSetSpeakerVolumes PROC
	jmp ImportFuncTbl[59 * 8]
BinkSetSpeakerVolumes ENDP
BinkSetVideoOnOff PROC
	jmp ImportFuncTbl[60 * 8]
BinkSetVideoOnOff ENDP
BinkSetVolume PROC
	jmp ImportFuncTbl[61 * 8]
BinkSetVolume ENDP
BinkSetWillLoop PROC
	jmp ImportFuncTbl[62 * 8]
BinkSetWillLoop ENDP
BinkShouldSkip PROC
	jmp ImportFuncTbl[63 * 8]
BinkShouldSkip ENDP
BinkStartAsyncThread PROC
	jmp ImportFuncTbl[64 * 8]
BinkStartAsyncThread ENDP
BinkUtilCPUs PROC
	jmp ImportFuncTbl[65 * 8]
BinkUtilCPUs ENDP
BinkUtilFree PROC
	jmp ImportFuncTbl[66 * 8]
BinkUtilFree ENDP
BinkUtilMalloc PROC
	jmp ImportFuncTbl[67 * 8]
BinkUtilMalloc ENDP
BinkUtilMutexCreate PROC
	jmp ImportFuncTbl[68 * 8]
BinkUtilMutexCreate ENDP
BinkUtilMutexDestroy PROC
	jmp ImportFuncTbl[69 * 8]
BinkUtilMutexDestroy ENDP
BinkUtilMutexLock PROC
	jmp ImportFuncTbl[70 * 8]
BinkUtilMutexLock ENDP
BinkUtilMutexLockTimeOut PROC
	jmp ImportFuncTbl[71 * 8]
BinkUtilMutexLockTimeOut ENDP
BinkUtilMutexUnlock PROC
	jmp ImportFuncTbl[72 * 8]
BinkUtilMutexUnlock ENDP
BinkUtilSoundGlobalLock PROC
	jmp ImportFuncTbl[73 * 8]
BinkUtilSoundGlobalLock ENDP
BinkUtilSoundGlobalUnlock PROC
	jmp ImportFuncTbl[74 * 8]
BinkUtilSoundGlobalUnlock ENDP
BinkWait PROC
	jmp ImportFuncTbl[75 * 8]
BinkWait ENDP
BinkWaitStopAsyncThread PROC
	jmp ImportFuncTbl[76 * 8]
BinkWaitStopAsyncThread ENDP
BinkWaitStopAsyncThreadsMulti PROC
	jmp ImportFuncTbl[77 * 8]
BinkWaitStopAsyncThreadsMulti ENDP
RADTimerRead PROC
	jmp ImportFuncTbl[78 * 8]
RADTimerRead ENDP
end
