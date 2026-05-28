from __future__ import annotations

from dataclasses import dataclass
import ast
from pathlib import Path
import re


_FRONTMATTER_DELIMITER = "---"


@dataclass(slots=True)
class SkillMetadata:
    name: str
    description: str
    path: Path
    allowed_tools: list[str] | None = None


@dataclass(slots=True)
class SkillMatch:
    skill: SkillMetadata
    score: int
    reason: str
    explicit: bool = False


class SkillManager:
    def __init__(self, skill_roots: list[Path]):
        self.skill_roots = [Path(root) for root in skill_roots]
        self._available: dict[str, SkillMetadata] = {}
        self._loaded: dict[str, str] = {}

    def discover(self) -> None:
        self._available.clear()
        self._loaded.clear()

        for root in self.skill_roots:
            if not root.exists() or not root.is_dir():
                continue

            for skill_file in sorted(root.rglob("SKILL.md")):
                if not skill_file.is_file():
                    continue

                metadata = self._parse_metadata(skill_file)
                self._available.setdefault(metadata.name, metadata)

    def list_skills(self) -> list[SkillMetadata]:
        return [self._available[name] for name in sorted(self._available)]

    def get_skill(self, name: str) -> SkillMetadata:
        try:
            return self._available[name]
        except KeyError as exc:
            raise KeyError(f"Unknown skill: {name}") from exc

    def has_skill(self, name: str) -> bool:
        return name in self._available

    def load_skill(self, name: str) -> str:
        if name in self._loaded:
            return self._loaded[name]

        metadata = self.get_skill(name)
        body = metadata.path.read_text(encoding="utf-8")
        body = self._strip_frontmatter(body)
        self._loaded[name] = body
        return body

    def get_loaded_skills(self) -> dict[str, str]:
        return dict(self._loaded)

    def get_loaded_skill(self, name: str) -> str | None:
        return self._loaded.get(name)

    def unload_skill(self, name: str) -> bool:
        return self._loaded.pop(name, None) is not None

    def get_active_skill_bodies(self, active_skills: list[str]) -> dict[str, str]:
        bodies: dict[str, str] = {}
        for name in active_skills:
            if name not in self._available:
                continue
            bodies[name] = self.load_skill(name)
        return bodies

    def render_index(self, active_skills: list[str] | None = None) -> str:
        active = set(active_skills or [])
        if not self._available:
            return "# Skills\n\nNo skills were discovered."

        lines = ["# Skills", ""]
        for skill in self.list_skills():
            marker = "*" if skill.name in active else "-"
            tools = ""
            if skill.allowed_tools:
                tools = f" | tools: {', '.join(skill.allowed_tools)}"
            lines.append(f"{marker} {skill.name}: {skill.description}{tools}")

        return "\n".join(lines)

    def suggest_skills(self, query: str, limit: int = 1) -> list[SkillMetadata]:
        return [
            match.skill
            for match in self.suggest_skill_matches(query, limit=limit)
        ]

    def suggest_skill_matches(
        self,
        query: str,
        limit: int = 1,
        min_score: int = 24,
    ) -> list[SkillMatch]:
        query_tokens = self._tokenize(query)
        if not query_tokens or not self._available:
            return []

        explicit_matches = self._find_explicit_skill_matches(query)
        if explicit_matches:
            explicit_matches.sort(key=lambda match: (-match.score, match.skill.name))
            return explicit_matches[:limit]

        scored: list[SkillMatch] = []
        for skill in self.list_skills():
            score, reason = self._score_skill(skill, query_tokens)
            if score >= min_score:
                scored.append(SkillMatch(skill=skill, score=score, reason=reason))

        scored.sort(key=lambda match: (-match.score, match.skill.name))
        if not scored:
            return []

        # Inferred activation should be conservative. Multiple active skills are
        # only safe when the user explicitly names more than one.
        return scored[:1]

    def _parse_metadata(self, skill_file: Path) -> SkillMetadata:
        text = skill_file.read_text(encoding="utf-8")
        frontmatter, body = self._split_frontmatter(text)
        folder_name = skill_file.parent.name
        name = frontmatter.get("name", "").strip() or folder_name
        description = self._extract_description(frontmatter, body, folder_name)
        allowed_tools = self._extract_allowed_tools(frontmatter)

        return SkillMetadata(
            name=name,
            description=description,
            path=skill_file,
            allowed_tools=allowed_tools,
        )

    def _split_frontmatter(self, text: str) -> tuple[dict[str, str], str]:
        lines = text.splitlines()
        if not lines or lines[0].strip() != _FRONTMATTER_DELIMITER:
            return {}, text

        end_index = None
        for index in range(1, len(lines)):
            if lines[index].strip() == _FRONTMATTER_DELIMITER:
                end_index = index
                break

        if end_index is None:
            return {}, text

        frontmatter = self._parse_frontmatter_lines(lines[1:end_index])
        body = "\n".join(lines[end_index + 1 :])
        return frontmatter, body

    def _parse_frontmatter_lines(self, lines: list[str]) -> dict[str, str]:
        data: dict[str, str] = {}
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or ":" not in line:
                continue

            key, value = line.split(":", 1)
            normalized_key = key.strip().lower()
            normalized_value = value.strip()
            normalized_key = normalized_key.replace("-", "_")
            if normalized_key in {"name", "description", "allowed_tools"}:
                data[normalized_key] = normalized_value

        return data

    def _extract_description(
        self,
        frontmatter: dict[str, str],
        body: str,
        fallback_name: str,
    ) -> str:
        description = frontmatter.get("description", "").strip()
        if description:
            return description

        paragraphs = [para.strip() for para in re.split(r"\n\s*\n", body) if para.strip()]
        for paragraph in paragraphs:
            lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
            if not lines:
                continue
            if lines[0].startswith("#"):
                continue
            return " ".join(lines)

        return fallback_name.replace("-", " ").replace("_", " ")

    def _extract_allowed_tools(self, frontmatter: dict[str, str]) -> list[str] | None:
        raw_value = frontmatter.get("allowed_tools")
        if not raw_value:
            return None

        parsed = self._parse_tool_list(raw_value)
        return parsed or None

    def _parse_tool_list(self, value: str) -> list[str]:
        text = value.strip()
        if not text:
            return []

        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]

        return [
            item.strip().strip("'\"")
            for item in text.split(",")
            if item.strip().strip("'\"")
        ]

    def _find_explicit_skill_matches(self, query: str) -> list[SkillMatch]:
        query_phrase = self._normalize_phrase(query)
        if not query_phrase:
            return []

        matches: list[SkillMatch] = []
        for skill in self.list_skills():
            for phrase in self._skill_name_phrases(skill.name):
                if self._contains_phrase(query_phrase, phrase):
                    matches.append(
                        SkillMatch(
                            skill=skill,
                            score=100 + len(phrase.split()),
                            reason="explicit skill name",
                            explicit=True,
                        )
                    )
                    break

        return matches

    def _skill_name_phrases(self, name: str) -> set[str]:
        phrase = self._normalize_phrase(name)
        phrases = {phrase} if phrase else set()

        if name.endswith("-design"):
            phrases.add(self._normalize_phrase(name.removesuffix("-design") + " design"))
        if name.endswith("-slides"):
            phrases.add(self._normalize_phrase(name.removesuffix("-slides") + " slides"))

        return {item for item in phrases if item}

    def _contains_phrase(self, query_phrase: str, phrase: str) -> bool:
        return f" {phrase} " in f" {query_phrase} "

    def _score_skill(self, skill: SkillMetadata, query_tokens: set[str]) -> tuple[int, str]:
        score = 0
        reasons: list[str] = []
        skill_name_tokens = self._tokenize(skill.name)
        skill_desc_tokens = self._tokenize(skill.description)
        ui_query_tokens = {
            "ui",
            "ux",
            "frontend",
            "frontend-design",
            "html",
            "css",
            "website",
            "webpage",
            "page",
            "pages",
            "landing",
            "dashboard",
            "app",
            "interface",
            "layout",
            "component",
            "components",
            "design",
        }
        slides_query_tokens = {"slide", "slides", "deck", "presentation", "presentations"}
        api_query_tokens = {"api", "apis", "endpoint", "endpoints", "interface", "contract"}

        name_overlap = skill_name_tokens & query_tokens
        desc_overlap = skill_desc_tokens & query_tokens
        if name_overlap:
            score += len(name_overlap) * 6
            reasons.append("skill name overlap")
        if desc_overlap:
            score += min(len(desc_overlap), 4)

        if skill_name_tokens and skill_name_tokens.issubset(query_tokens):
            score += 18
            reasons.append("all skill name terms present")

        if skill.name == "frontend-design" and ui_query_tokens & query_tokens:
            score += 28
            reasons.append("frontend UI/design request")

        if skill.name == "frontend-slides" and slides_query_tokens & query_tokens:
            score += 28
            reasons.append("frontend slide/deck request")

        if "api" in skill_name_tokens and api_query_tokens & query_tokens:
            score += 24
            reasons.append("API/interface request")

        if not reasons:
            reasons.append("keyword match")

        return score, ", ".join(dict.fromkeys(reasons))

    def _tokenize(self, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]+", text.lower())
            if token
        }

    def _normalize_phrase(self, text: str) -> str:
        return " ".join(
            token
            for token in re.findall(r"[a-z0-9]+", text.lower())
            if token
        )

    def _strip_frontmatter(self, text: str) -> str:
        frontmatter, body = self._split_frontmatter(text)
        if frontmatter:
            return body.lstrip("\n")
        return text
