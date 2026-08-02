import os
import json
import subprocess
import shutil
from multiprocessing import Pool, cpu_count
from pathlib import Path

# --- Configuration ---
SOURCE_REPO_URL = "https://github.com/ArknightsAssets/ArknightsAssets2"
SOURCE_DIR = "source"
SOURCES_JSON = ".sources.json"

# Mapping: "Source Folder inside external repo" -> "Local Destination Folder"
FOLDERS_MAPPING = {
    "assets/dyn/arts/charavatars": "assets/avatars",
    "assets/dyn/arts/charportraits": "assets/portraits",
    "assets/dyn/arts/characters": "assets/arts",
    "assets/dyn/arts/skills": "assets/skills",
    "assets/dyn/arts/rarity_hub": "assets/ui/stars",
    "assets/dyn/arts/elite_hub": "assets/ui/elite",
    "assets/dyn/arts/potential_hub": "assets/ui/potential",
    "assets/dyn/arts/ui/[uc]charcommon/dynprofession": "assets/ui/profession",
    "assets/dyn/arts/ui/subprofessionicon": "assets/ui/subprofession",
    "assets/dyn/arts/number_hub": "assets/ui/skill_level",
    "assets/dyn/arts/specialized_hub": "assets/ui/skill_mastery",
    "assets/dyn/arts/uniequipimg": "assets/module_img",
    "assets/dyn/arts/ui/uniequiptype": "assets/ui/module_type",
    "assets/dyn/ui/[pack]commoncharselect/common_char_select_default_card_panel": "assets/ui/char_card",
    "assets/dyn/avg/characters": "assets/story/characters",
    "assets/dyn/avg/backgrounds": "assets/story/backgrounds",
    "assets/dyn/avg/images": "assets/story/images",
    "assets/dyn/avg/items": "assets/story/items",
    "assets/dyn/avg/animatedkv": "assets/story/animatedkv",
}


def run_command(cmd, cwd=None):
    """Helper to run shell commands."""
    subprocess.run(cmd, check=True, shell=True,
                   cwd=cwd, stdout=subprocess.PIPE)


def get_last_sha():
    """Reads the last synced SHA from .sources.json"""
    if not os.path.exists(SOURCES_JSON):
        return None
    try:
        with open(SOURCES_JSON, "r") as f:
            data = json.load(f)
            return data.get("ArknightsAssets")
    except:
        return None


def save_new_sha(sha):
    """Updates the .sources.json file"""
    data = {}
    if os.path.exists(SOURCES_JSON):
        with open(SOURCES_JSON, "r") as f:
            data = json.load(f)

    data["ArknightsAssets"] = sha
    with open(SOURCES_JSON, "w") as f:
        json.dump(data, f, indent=2)


def convert_image(task):
    """Worker function to convert a single image."""
    src_path, dst_path = task

    # Ensure directory exists (race condition safe)
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    # Run cwebp
    cmd = ["cwebp", src_path, "-o", dst_path, "-quiet"]
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError:
        print(f"Error converting: {src_path}")
        return False


def main():
    # 1. Setup Source Repo
    if not os.path.exists(SOURCE_DIR):
        print(f"Cloning {SOURCE_REPO_URL}...")
        run_command(f"git clone --depth=1 -b cn --filter=blob:none --sparse {
            SOURCE_REPO_URL} {SOURCE_DIR}")
        print("Cloning done")

        # Configure sparse checkout
        cwd = os.getcwd()
        os.chdir(SOURCE_DIR)
        sparse_paths = (
            " ".join(FOLDERS_MAPPING.keys()).replace(
                "[", "\\[").replace("]", "\\]")
        )
        run_command(f"git sparse-checkout set {sparse_paths} --skip-checks")
        os.chdir(cwd)
    else:
        print("Updating source repo...")
        run_command("git pull", cwd=SOURCE_DIR)

    # 2. Determine Changed Files
    last_sha = get_last_sha()
    current_sha = (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=SOURCE_DIR)
        .decode()
        .strip()
    )

    if last_sha == current_sha:
        print("Already up to date.")
        return

    print(f"Syncing from {
          last_sha if last_sha else 'beginning'} to {current_sha}")

    changed_files = []
    if last_sha:
        # Get diff
        cmd = ["git", "diff", "--name-only", last_sha, "HEAD"]
        output = subprocess.check_output(cmd, cwd=SOURCE_DIR).decode().strip()
        changed_files = output.split("\n") if output else []
    else:
        # First run: get all files
        cmd = ["git", "ls-files"]
        output = subprocess.check_output(cmd, cwd=SOURCE_DIR).decode().strip()
        changed_files = output.split("\n") if output else []

    # 3. Prepare Tasks
    tasks = []
    for fpath in changed_files:
        if not fpath.strip():
            continue

        matched_src_folder = None
        for src_folder in FOLDERS_MAPPING:
            if fpath.startswith(src_folder) and fpath.endswith(".png"):
                matched_src_folder = src_folder
                break

        if matched_src_folder:
            target_folder = FOLDERS_MAPPING[matched_src_folder]
            rel_path = os.path.relpath(fpath, matched_src_folder)
            full_src = os.path.join(SOURCE_DIR, fpath)

            file_name = os.path.splitext(rel_path)[0] + ".webp"
            full_dst = os.path.join(target_folder, file_name)

            tasks.append((full_src, full_dst))

    # 4. Process in Parallel
    if not tasks:
        print("No matching images found to convert.")
    else:
        print(f"Converting {len(tasks)} images using {cpu_count()} cores...")
        # Use a Pool to run conversions in parallel
        with Pool(cpu_count()) as p:
            p.map(convert_image, tasks)

    # 5. Save state
    save_new_sha(current_sha)
    print("Done! You can now commit the changes.")


if __name__ == "__main__":
    main()
