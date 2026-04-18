#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from collections import defaultdict, deque

import yaml
import hashlib
import json


# ---------------- utils ----------------

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes())


def git_head_hash(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo
    ).decode().strip()


def run(cmd, *, cwd=None, env=None):
    print(f"+ {cmd}")
    subprocess.run(cmd, shell=True, check=True, cwd=cwd, env=env)


def apply_metavars(text, vars):
    for k, v in vars.items():
        text = text.replace(f"@@{k}@@", str(v))
    return text


def parse_arch(triple: str) -> str:
    return triple.split("-", 1)[0]


def alt_arch(arch: str) -> str:
    if arch == "x86_64":
        return "amd64"
    else:
        return arch


def compute_node_signature(node, *, source_dir, triple, dep_stamps):
    h = hashlib.sha256()

    # node definition (stable order)
    relevant = {
        "name": node["name"],
        "source": node["source"],
        "configure": normalize_phase(node.get("configure")),
        "build": normalize_phase(node.get("build")),
        "install": normalize_phase(node.get("install")),
    }
    h.update(json.dumps(relevant, sort_keys=True).encode())

    # target
    h.update(triple.encode())

    # source commit
    h.update(git_head_hash(source_dir).encode())

    # dependency stamps
    for dep in sorted(dep_stamps):
        h.update(dep.encode())

    return h.hexdigest()


def load_stamp(build_dir: Path) -> str | None:
    stamp = build_dir / ".build-stamp"
    if stamp.exists():
        return stamp.read_text().strip()
    return None


def write_stamp(build_dir: Path, value: str):
    (build_dir / ".build-stamp").write_text(value + "\n")


def normalize_phase(value):
    """
    Normalize a build phase into a list of shell commands.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        if not all(isinstance(v, str) for v in value):
            raise TypeError("Build phase arrays must contain only strings")
        return value
    raise TypeError("Build phase must be a string or list of strings")


def already_configured(build_dir: Path) -> bool:
    # Meson
    if (build_dir / "meson-private").exists():
        return True
    if (build_dir / "build.ninja").exists():
        return True

    # CMake
    if (build_dir / "CMakeCache.txt").exists():
        return True

    # Autotools / generic Makefile
    if (build_dir / "Makefile").exists():
        return True

    return False


# ---------------- yaml loading ----------------

def load_yaml_recursive(path: Path, seen=None):
    if seen is None:
        seen = set()

    path = path.resolve()
    if path in seen:
        return {}

    seen.add(path)

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    merged = {
        "imports": [],
        "sources": [],
        "tools": [],
        "packages": [],
    }

    for imp in data.get("imports", []):
        imp_path = (path.parent / imp).resolve()
        sub = load_yaml_recursive(imp_path, seen)
        for k in merged:
            merged[k].extend(sub.get(k, []))

    for k in merged:
        merged[k].extend(data.get(k, []))

    return merged


# ---------------- dependency resolution ----------------

def topo_sort(nodes):
    graph = defaultdict(list)
    indeg = defaultdict(int)

    for name in nodes:
        indeg[name] = 0

    for name, node in nodes.items():
        for dep in node.get("_deps", []):
            graph[dep].append(name)
            indeg[name] += 1

    q = deque([n for n, d in indeg.items() if d == 0])
    order = []

    while q:
        n = q.popleft()
        order.append(n)
        for m in graph[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)

    if len(order) != len(nodes):
        raise RuntimeError("Dependency cycle detected")

    return order


# ---------------- main ----------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-dir", required=True,
                    help="Source tree containing build.yml")
    ap.add_argument("--triple", required=True)
    args = ap.parse_args()

    source_root = Path(args.source_dir).resolve()
    build_yml = source_root / "build.yml"

    if not build_yml.exists():
        sys.exit("build.yml not found in source directory")

    triple = args.triple
    arch = parse_arch(triple)

    data = load_yaml_recursive(build_yml)

    build_root = Path.cwd().resolve()

    toolchain = build_root / "toolchain"
    sysroot = build_root / "sysroot"
    sources_dir = build_root / "sources"
    config_dir = build_root / "config"

    for d in (toolchain, sysroot, sources_dir, config_dir):
        d.mkdir(parents=True, exist_ok=True)

    # ---- fetch sources ----
    sources = {}
    for src in data["sources"]:
        name = src["name"]
        repo = src["git"]
        depth = src.get("depth", 1)
        ref = src.get("ref")

        dst = sources_dir / name

        if not dst.exists():
            clone_cmd = ["git", "clone", f"--depth={depth}", repo, str(dst)]
            run(" ".join(clone_cmd))
        else:
            # sanity check: is it a git repo?
            if not (dst / ".git").exists():
                sys.exit(f"{dst} exists but is not a git repository")
            
            print(f"Using existing source: {name}")

            fetch_cmd = ["git", "fetch", "--all"]
            if depth:
                fetch_cmd += [f"--depth={depth}"]
            run(" ".join(fetch_cmd), cwd=dst)

        # Checkout ref if specified
        if ref:
            run(f"git checkout {ref}", cwd=dst)
        else:
            # Fast-forward to latest on current branch
            run("git pull --ff-only", cwd=dst)

        sources[name] = dst

    # ---- copy config directory (once) ----
    src_config = source_root / "config"
    if src_config.exists():
        shutil.copytree(src_config, config_dir, dirs_exist_ok=True)

    # ---- metavariables ----
    metavars = {
        "TOOLCHAIN": toolchain,
        "SYSROOT": sysroot,
        "ARCH": arch,
        "TRIPLE": triple,
        "CONFIG": config_dir,
        "ARCH_ALT": alt_arch(arch),
    }

    # ---- patch config files ----
    for path in config_dir.rglob("*"):
        if path.is_file():
            path.write_text(
                apply_metavars(path.read_text(), metavars)
            )

    # ---- collect build nodes ----
    nodes = {}

    def register(node, kind):
        node = dict(node)
        node["_kind"] = kind
        node["_deps"] = []
        nodes[kind + "-" + node["name"]] = node

    for t in data["tools"]:
        register(t, "tool")

    for p in data["packages"]:
        register(p, "package")

    # ---- dependencies ----
    for node in nodes.values():
        node["_deps"].extend(["package-" + i for i in node.get("depends", [])])
        node["_deps"].extend(["tool-" + i for i in node.get("require-tools", [])])

    order = topo_sort(nodes)

    print()
    for node in order:
        print(f"`{node}` from `{nodes[node]["source"]}` (requires {", ".join(nodes[node]["_deps"])})")

    # ---- build loop ----
    built_stamps = {}

    for name in order:
        node = nodes[name]
        print(f"\n=== {node['_kind'].upper()} {name.split("-", 1)[1]} ===")

        src = sources[node["source"]]
        build_dir = build_root / f"build-{name}"
        build_dir.mkdir(parents=True, exist_ok=True)

        metavars["SOURCES"] = src

        dep_stamps = [built_stamps[d] for d in node["_deps"]]
        new_sig = compute_node_signature(
            node,
            source_dir=src,
            triple=triple,
            dep_stamps=dep_stamps,
        )

        old_sig = load_stamp(build_dir)

        if old_sig == new_sig:
            print(f"✓ {name} unchanged — skipping")
            built_stamps[name] = old_sig
            phases = ("install",)
        else:
            print(f"↻ rebuilding {name}")
            phases = ("configure", "build", "install")

        for phase in phases:
            if phase in node:
                if phase == "configure" and already_configured(build_dir):
                    print(f"↪ configure already done for {name}, skipping")
                    continue

                for cmd in normalize_phase(node.get(phase)):
                    cmd = apply_metavars(cmd, metavars)
                    run(cmd, cwd=build_dir)
        
        write_stamp(build_dir, new_sig)
        built_stamps[name] = new_sig

    print("\nBuild completed successfully")
    print(f"Build directory: {build_root}")


if __name__ == "__main__":
    main()
