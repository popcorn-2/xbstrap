## Building Popcorn

Requires LLVM 18 or above.

Create a new clean directory with `mkdir popcorn` and navigate into it with `cd popcorn`.

Clone `popcorn-2` with `git clone https://github.com/popcorn-2/popcorn-2.git`, and `xbstrap` with `git clone https://github.com/popcorn-2/xbstrap.git`.

Create a new build directory with `mkdir build` and `cd` into it.

Run `../xbstrap/pop --sysroot=../root/disk --target=x86_64-unknown-popcorn --local-source @core/kernel=../popcorn-2 build @core/kernel` to build `popcorn-2` and install all the tools for the target machine in `popcorn/root/`.

Note that by default, `pop` will automatically download all the LLVM and Rust tools required to build. If you want, you have the option of building locally instead.

### Building the LLVM dependency

Run `../xbstrap/pop --sysroot=../root/disk --target=x86_64-unknown-popcorn --as-build-dep --from-source=@dev/llvm package @dev/llvm:lld,clang,clang-extra-tools`.

This builds with the features `lld`, `clang` and `clang-extra-tools` enabled.

### Building the Rust dependency

Run `../xbstrap/pop --sysroot=../root/disk --target=x86_64-unknown-popcorn --as-build-dep --from-source=@dev/rustc package @dev/rustc:cargo,rustdoc,clippy,docs,src,rustfmt`.

This builds with the features `cargo`, `rustdoc`, `clippy`, `docs`, `src` and `rustfmt` enabled.