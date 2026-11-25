@echo off
cd /d "e:\works\chess"
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul 2>&1
if not exist egtb_build mkdir egtb_build
cd egtb_build
del *.obj *.exe *.log 2>nul

echo [1/3] compile lzma C files (only LzmaDec needed for probing)
cl /c /O2 /I..\egtb_src\lzma ..\egtb_src\lzma\LzmaDec.c >>build.log 2>&1
if not exist LzmaDec.obj (echo FAILED lzma & type build.log & exit /b 1)

echo [2/3] compile Egtb C++ files
cl /c /O2 /std:c++14 /EHsc /FIcassert /FIcctype /FIcstdio /I..\egtb_src /I..\egtb_src\lzma ..\egtb_src\Egtb.cpp ..\egtb_src\EgtbBoard.cpp ..\egtb_src\EgtbDb.cpp ..\egtb_src\EgtbFile.cpp ..\egtb_src\EgtbKey.cpp ..\egtb_src\EgtbLookup.cpp ..\egtb_src\probe_cli.cpp >>build.log 2>&1
if not exist probe_cli.obj (echo FAILED cpp & type build.log & exit /b 1)

echo [3/3] link
link /OUT:egtb_probe.exe *.obj >>build.log 2>&1
if not exist egtb_probe.exe (echo FAILED link & type build.log & exit /b 1)

echo [OK] built egtb_probe.exe
exit /b 0
