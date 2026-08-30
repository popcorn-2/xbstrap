## Building Popcorn

Requires LLVM 18 or above.

Create a top-level directory with `mkdir popcorn` and navigate into it with `cd popcorn`.

Clone `xbstrap` with `git clone https://github.com/popcorn-2/xbstrap.git`.

Create a new build directory with `mkdir build` and `cd` into it.

Run `../xbstrap/pop --sysroot=../root/disk --target=x86_64-unknown-popcorn install @core/kernel` to build `popcorn-2` and install all the tools for the target machine in `popcorn/root/`.

Note that, by default, this downloads `popcorn-2` along with the required pre-built LLVM and Rust tools automatically. If you wish to contribute, you may wish to do these steps manually, the steps of which are detailed in the following sub-sections.

### Building the LLVM tooling

Run `../xbstrap/pop --target=x86_64-unknown-popcorn --as-build-dep --from-source=@dev/llvm package @dev/llvm:lld,clang,clang-tools-extra`.

This builds with the features `lld`, `clang` and `clang-tools-extra` enabled.

### Building the Rust tooling

Run `../xbstrap/pop --target=x86_64-unknown-popcorn --as-build-dep --from-source=@dev/rustc package @dev/rustc:cargo,rustdoc,clippy,docs,src,rustfmt`.

This builds with the features `cargo`, `rustdoc`, `clippy`, `docs`, `src` and `rustfmt` enabled.

### Cloning Popcorn

Clone `popcorn-2` with `git clone https://github.com/popcorn-2/popcorn-2.git` into the top-level `popcorn` directory and navigate inside it.

Initialise the submodules with `git submodule init`, then update with `git submodule update`.

Build by navigating back to `build` and running `../xbstrap/pop --sysroot=../root/disk --target=x86_64-unknown-popcorn --local-source @core/kernel=../popcorn-2 install @core/kernel`.