from pathlib import Path
import re
import subprocess
from dataclasses import dataclass
from pydantic import BaseModel, Field
from agentforge_harness.tools.base import Tool, ToolConfirmation, ToolInvocation, ToolKind, ToolResult


class PatchParams(BaseModel):
    intent: str | None = Field(
        None,
        description=(
            "Short natural-language description of why this patch is being applied. "
            "This is shown to the user during approval and stored in metadata."
        ),
    )
    patch: str = Field(
        ...,
        description=(
            "A unified diff to apply to the workspace. The patch may modify one "
            "or more files and should use standard git-style paths such as "
            "'a/path.py' and 'b/path.py'."
        ),
    )
    dry_run: bool = Field(
        False,
        description=(
            "Validate the patch without writing changes. Use this when checking "
            "whether a patch can apply cleanly before making edits."
        ),
    )
    strip: int = Field(
        1,
        ge=0,
        le=5,
        description=(
            "Number of leading path components to strip while applying the patch. "
            "Use 1 for standard git diffs with 'a/' and 'b/' prefixes."
        ),
    )
    create_parent_dirs: bool = Field(
        True,
        description=(
            "Create missing parent directories for newly-created files when the "
            "fallback patch engine is used. Set false when parent directories "
            "must already exist."
        ),
    )


@dataclass
class ParsedHunk:
    old_start: int
    old_lines: list[str]
    new_lines: list[str]


@dataclass
class ParsedFilePatch:
    path: str
    hunks: list[ParsedHunk]
    is_new_file: bool = False
    is_deletion: bool = False


def _strip_path_components(path: str, strip: int) -> str:
    parts = Path(path).parts
    if strip <= 0:
        return path
    if len(parts) <= strip:
        return ""
    return str(Path(*parts[strip:]))


def _normalize_patch_header_path(raw_path: str, strip: int) -> str | None:
    path = raw_path.strip().split("\t", 1)[0]
    if path == "/dev/null":
        return None

    normalized = _strip_path_components(path, strip)
    return normalized or None


def extract_patch_paths(patch: str, strip: int) -> list[str]:
    paths: set[str] = set()

    for line in patch.splitlines():
        if not (line.startswith("--- ") or line.startswith("+++ ")):
            continue

        path = _normalize_patch_header_path(line[4:], strip)
        if path:
            paths.add(path)

    return sorted(paths)


def normalize_patch_text(patch: str) -> str:
    normalized = patch.replace("\n\\\\ No newline at end of file", "\n\\ No newline at end of file")
    if not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def validate_patch_paths(cwd: Path, paths: list[str]) -> list[Path]:
    root = cwd.resolve()
    resolved_paths: list[Path] = []

    for path in paths:
        candidate = Path(path)
        if candidate.is_absolute():
            raise ValueError(f"Absolute paths are not allowed in patches: {path}")
        if ".." in candidate.parts:
            raise ValueError(f"Parent traversal is not allowed in patches: {path}")
        if ".git" in candidate.parts:
            raise ValueError(f"Refusing to patch git internals: {path}")

        resolved = (root / candidate).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"Patch path escapes workspace: {path}")

        resolved_paths.append(resolved)

    return resolved_paths


def run_git_apply(cwd: Path, patch: str, strip: int, check_only: bool) -> subprocess.CompletedProcess[str]:
    command = ["git", "apply", f"-p{strip}", "--whitespace=nowarn"]
    if check_only:
        command.append("--check")

    return subprocess.run(
        command,
        input=patch,
        text=True,
        cwd=cwd,
        capture_output=True,
    )


def _parse_hunk_header(line: str) -> int | None:
    match = re.match(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", line)
    if not match:
        return None
    return int(match.group(1))


def _parse_unified_patch(patch: str, strip: int) -> list[ParsedFilePatch]:
    lines = patch.splitlines()
    file_patches: list[ParsedFilePatch] = []
    index = 0

    while index < len(lines):
        if not lines[index].startswith("--- "):
            index += 1
            continue

        old_path = _normalize_patch_header_path(lines[index][4:], strip)
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise ValueError("Patch has a file header without a matching +++ header")

        new_path = _normalize_patch_header_path(lines[index][4:], strip)
        path = new_path or old_path
        if not path:
            raise ValueError("Patch contains a file header without a usable path")
        is_new_file = old_path is None and new_path is not None
        is_deletion = new_path is None and old_path is not None

        index += 1
        hunks: list[ParsedHunk] = []

        while index < len(lines) and not lines[index].startswith("--- "):
            if not lines[index].startswith("@@ "):
                index += 1
                continue

            old_start = _parse_hunk_header(lines[index])
            if old_start is None:
                raise ValueError(f"Invalid hunk header: {lines[index]}")

            index += 1
            old_lines: list[str] = []
            new_lines: list[str] = []
            previous_groups: list[list[str]] = []

            while (
                index < len(lines)
                and not lines[index].startswith("@@ ")
                and not lines[index].startswith("--- ")
            ):
                line = lines[index]
                if line.startswith("\\ No newline at end of file"):
                    for group in previous_groups:
                        if group and group[-1].endswith("\n"):
                            group[-1] = group[-1][:-1]
                    index += 1
                    continue

                if not line:
                    raise ValueError("Invalid empty patch hunk line")

                marker = line[0]
                content = line[1:] + "\n"

                if marker == " ":
                    old_lines.append(content)
                    new_lines.append(content)
                    previous_groups = [old_lines, new_lines]
                elif marker == "-":
                    old_lines.append(content)
                    previous_groups = [old_lines]
                elif marker == "+":
                    new_lines.append(content)
                    previous_groups = [new_lines]
                else:
                    raise ValueError(f"Invalid patch hunk line: {line}")

                index += 1

            hunks.append(ParsedHunk(old_start=old_start, old_lines=old_lines, new_lines=new_lines))

        file_patches.append(
            ParsedFilePatch(
                path=path,
                hunks=hunks,
                is_new_file=is_new_file,
                is_deletion=is_deletion,
            )
        )

    if not file_patches:
        raise ValueError("Patch does not contain any parseable file hunks")

    return file_patches


def _lines_match(current: list[str], expected: list[str]) -> bool:
    if current == expected:
        return True
    if len(current) != len(expected):
        return False
    return all(
        current_line.rstrip("\r\n") == expected_line.rstrip("\r\n")
        for current_line, expected_line in zip(current, expected)
    )


def _find_hunk_position(lines: list[str], old_lines: list[str], preferred_index: int) -> int | None:
    if not old_lines:
        return max(0, min(preferred_index, len(lines)))

    candidates = [preferred_index]
    candidates.extend(
        idx
        for idx in range(max(0, preferred_index - 3), min(len(lines), preferred_index + 4))
        if idx != preferred_index
    )
    candidates.extend(idx for idx in range(0, len(lines) + 1) if idx not in candidates)

    for index in candidates:
        current = lines[index : index + len(old_lines)]
        if _lines_match(current, old_lines):
            return index

    return None


def apply_patch_fallback(
    cwd: Path,
    patch: str,
    strip: int,
    dry_run: bool,
    create_parent_dirs: bool = True,
) -> list[Path]:
    file_patches = _parse_unified_patch(patch, strip)
    affected_paths = validate_patch_paths(cwd, [file_patch.path for file_patch in file_patches])
    new_contents: dict[Path, str] = {}
    deletions: list[Path] = []

    for file_patch, path in zip(file_patches, affected_paths):
        if file_patch.is_new_file and not path.parent.exists() and not create_parent_dirs:
            raise ValueError(
                f"Parent directory does not exist for new file: {file_patch.path}. "
                "Set create_parent_dirs=true or create the directory first."
            )

        if file_patch.is_deletion and not path.exists():
            raise ValueError(f"Cannot delete missing file: {file_patch.path}")

        content = path.read_text(encoding="utf-8") if path.exists() else ""
        lines = content.splitlines(keepends=True)
        offset = 0

        for hunk in file_patch.hunks:
            preferred_index = max(0, hunk.old_start - 1 + offset)
            position = _find_hunk_position(lines, hunk.old_lines, preferred_index)
            if position is None:
                raise ValueError(
                    f"Could not match patch hunk for {file_patch.path} near line {hunk.old_start}"
                )

            lines = lines[:position] + hunk.new_lines + lines[position + len(hunk.old_lines) :]
            offset += len(hunk.new_lines) - len(hunk.old_lines)

        if file_patch.is_deletion:
            deletions.append(path)
        else:
            new_contents[path] = "".join(lines)

    if not dry_run:
        for path in deletions:
            path.unlink()
        for path, content in new_contents.items():
            if create_parent_dirs:
                path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    return affected_paths


def validate_parent_directory_policy(
    cwd: Path,
    patch: str,
    strip: int,
    create_parent_dirs: bool,
) -> None:
    if create_parent_dirs:
        return

    file_patches = _parse_unified_patch(patch, strip)
    affected_paths = validate_patch_paths(cwd, [file_patch.path for file_patch in file_patches])

    for file_patch, path in zip(file_patches, affected_paths):
        if file_patch.is_new_file and not path.parent.exists():
            raise ValueError(
                f"Parent directory does not exist for new file: {file_patch.path}. "
                "Set create_parent_dirs=true or create the directory first."
            )


class ApplyPatchTool(Tool):
    name = "apply_patch"
    description = (
        "Apply a unified diff to one or more files in the workspace. Use this "
        "for coherent multi-file edits when a change is easier to express as a "
        "patch than as repeated exact string replacements. Pass the patch text "
        "directly to this tool; do not create a .patch file unless the user "
        "explicitly asks for one. Use dry_run=true to validate a patch before "
        "writing changes. The patch must exactly match current file contents, "
        "including whitespace and final-newline state. If git-style patch "
        "validation fails, the tool attempts a narrow line-based fallback for "
        "simple text patches. For creating or replacing a single whole file, "
        "prefer write_file, and for a small surgical edit, prefer edit."
    )
    kind = ToolKind.WRITE
    schema = PatchParams

    def is_mutating(self, params: dict[str, object]) -> bool:
        try:
            return not PatchParams(**params).dry_run
        except Exception:
            return True

    async def get_confirmation(
        self,
        invocation: ToolInvocation,
    ) -> ToolConfirmation | None:
        params = PatchParams(**invocation.params)
        patch = normalize_patch_text(params.patch)
        if params.dry_run:
            return None

        paths = extract_patch_paths(patch, params.strip)

        affected_paths: list[Path] = []
        try:
            affected_paths = validate_patch_paths(invocation.cwd, paths)
        except ValueError:
            pass

        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=params.intent or f"Apply patch to {len(paths)} file(s)",
            affected_paths=affected_paths,
            diff_text=patch,
            is_dangerous=True,
        )

    def _patch_failure_hint(self) -> str:
        return (
            "\n\nHint: The patch context did not match the current file bytes. "
            "Re-read the target file and check exact whitespace, stale content, "
            "and whether the file has no trailing newline. If the target has no "
            "final newline, include '\\ No newline at end of file' markers in the patch."
        )

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = PatchParams(**invocation.params)
        patch = normalize_patch_text(params.patch)
        cwd = invocation.cwd.resolve()

        paths = extract_patch_paths(patch, params.strip)
        if not paths:
            return ToolResult.error_result("Patch does not contain any file paths")

        try:
            affected_paths = validate_patch_paths(cwd, paths)
            validate_parent_directory_policy(
                cwd,
                patch,
                params.strip,
                params.create_parent_dirs,
            )
        except ValueError as e:
            return ToolResult.error_result(
                str(e),
                summary="Patch path validation failed",
                diff_text=patch,
                recovery_hint="Fix the patch paths or parent directory policy, then retry.",
                metadata={
                    "paths": paths,
                    "dry_run": params.dry_run,
                    "strip": params.strip,
                    "intent": params.intent,
                    "create_parent_dirs": params.create_parent_dirs,
                },
            )

        check = run_git_apply(cwd, patch, params.strip, check_only=True)
        if check.returncode != 0:
            strict_output = check.stderr or check.stdout
            try:
                fallback_paths = apply_patch_fallback(
                    cwd,
                    patch,
                    params.strip,
                    dry_run=True,
                    create_parent_dirs=params.create_parent_dirs,
                )
                if params.dry_run:
                    return ToolResult.success_result(
                        f"Patch check passed with fallback for {len(fallback_paths)} file(s)",
                        diff_text=patch,
                        summary=f"Patch check passed with fallback for {len(fallback_paths)} file(s)",
                        artifacts=[str(path) for path in fallback_paths],
                        next_actions=["Run apply_patch with dry_run=false to apply this patch."],
                        metadata={
                            "paths": [str(path) for path in fallback_paths],
                            "dry_run": True,
                            "strip": params.strip,
                            "intent": params.intent,
                            "create_parent_dirs": params.create_parent_dirs,
                            "fallback": True,
                        },
                    )
            except Exception as fallback_error:
                output = strict_output + f"\nFallback apply check failed: {fallback_error}"
                return ToolResult.error_result(
                    "Patch check failed",
                    output=output + self._patch_failure_hint(),
                    diff_text=patch,
                    summary="Patch check failed",
                    artifacts=[str(path) for path in affected_paths],
                    recovery_hint="Re-read the target file, fix stale context or whitespace, then retry. For append-only changes, prefer append_file.",
                    metadata={
                        "paths": [str(path) for path in affected_paths],
                        "dry_run": True,
                        "strip": params.strip,
                        "intent": params.intent,
                        "create_parent_dirs": params.create_parent_dirs,
                    },
                )

            try:
                fallback_paths = apply_patch_fallback(
                    cwd,
                    patch,
                    params.strip,
                    dry_run=False,
                    create_parent_dirs=params.create_parent_dirs,
                )
            except Exception as fallback_error:
                output = strict_output + f"\nFallback apply failed: {fallback_error}"
                return ToolResult.error_result(
                "Patch check failed",
                output=output + self._patch_failure_hint(),
                diff_text=patch,
                summary="Patch check failed",
                artifacts=[str(path) for path in affected_paths],
                recovery_hint="Re-read the target file, fix stale context or whitespace, then retry. For append-only changes, prefer append_file.",
                metadata={
                        "paths": [str(path) for path in affected_paths],
                        "dry_run": False,
                        "strip": params.strip,
                        "intent": params.intent,
                        "create_parent_dirs": params.create_parent_dirs,
                    },
                )

            return ToolResult.success_result(
                f"Applied patch with fallback to {len(fallback_paths)} file(s)",
                diff_text=patch,
                summary=f"Applied patch with fallback to {len(fallback_paths)} file(s)",
                artifacts=[str(path) for path in fallback_paths],
                next_actions=["Use read_file or tests to verify the changed file behavior."],
                metadata={
                    "paths": [str(path) for path in fallback_paths],
                    "dry_run": False,
                    "strip": params.strip,
                    "intent": params.intent,
                    "create_parent_dirs": params.create_parent_dirs,
                    "fallback": True,
                },
            )

        if params.dry_run:
            return ToolResult.success_result(
                f"Patch check passed for {len(affected_paths)} file(s)",
                diff_text=patch,
                summary=f"Patch check passed for {len(affected_paths)} file(s)",
                artifacts=[str(path) for path in affected_paths],
                next_actions=["Run apply_patch with dry_run=false to apply this patch."],
                metadata={
                    "paths": [str(path) for path in affected_paths],
                    "dry_run": True,
                    "strip": params.strip,
                    "intent": params.intent,
                    "create_parent_dirs": params.create_parent_dirs,
                },
            )

        result = run_git_apply(cwd, patch, params.strip, check_only=False)
        if result.returncode != 0:
            output = result.stderr or result.stdout
            return ToolResult.error_result(
                "Patch apply failed",
                output=output + self._patch_failure_hint(),
                diff_text=patch,
                summary="Patch apply failed",
                artifacts=[str(path) for path in affected_paths],
                recovery_hint="Re-read the target file, fix stale context or whitespace, then retry. For append-only changes, prefer append_file.",
                metadata={
                    "paths": [str(path) for path in affected_paths],
                    "dry_run": False,
                    "strip": params.strip,
                    "intent": params.intent,
                    "create_parent_dirs": params.create_parent_dirs,
                },
            )

        return ToolResult.success_result(
            f"Applied patch to {len(affected_paths)} file(s)",
            diff_text=patch,
            summary=f"Applied patch to {len(affected_paths)} file(s)",
            artifacts=[str(path) for path in affected_paths],
            next_actions=["Use read_file or tests to verify the changed file behavior."],
            metadata={
                "paths": [str(path) for path in affected_paths],
                "dry_run": False,
                "strip": params.strip,
                "intent": params.intent,
                "create_parent_dirs": params.create_parent_dirs,
            },
        )
