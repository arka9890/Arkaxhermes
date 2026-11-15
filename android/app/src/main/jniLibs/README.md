# Native library proot

`scripts/fetch-proot.sh --abi arm64-v8a` mengisi:

```
arm64-v8a/libproot.so           ← biner proot (Termux atau build NDK)
arm64-v8a/libproot-loader.so    ← loader, bila diperlukan rilis Termux
arm64-v8a/libtalloc.so          ← dependency, bila ada
x86_64/…                        ← untuk emulator (rootfs amd64)
```

**Kenapa `.so`?** Android 10+ (API 29) melarang `execve()` pada berkas di `filesDir` yang writable. `ProotRuntime.kt` menjalankan `applicationInfo.nativeLibraryDir + "/libproot.so"`, dan manifest memakai `android:extractNativeLibs="true"` + `jniLibs.useLegacyPackaging = true` agar berkas benar-benar ada di disk.

Berkas biner tidak disimpan di git (`.gitignore`). Sumber: [termux/proot](https://github.com/termux/proot), GPL-2.0-or-later.
