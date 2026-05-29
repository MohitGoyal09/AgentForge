from pathlib import Path

from skills.manager import SkillManager


def write_skill(root: Path, name: str, description: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                "---",
                "",
                f"# {name}",
                "",
                "Skill body.",
            ]
        ),
        encoding="utf-8",
    )


def write_skill_with_frontmatter(root: Path, folder: str, frontmatter: list[str]) -> None:
    skill_dir = root / folder
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                *frontmatter,
                "---",
                "",
                "# Skill",
                "",
                "Skill body.",
            ]
        ),
        encoding="utf-8",
    )


def test_explicit_skill_name_only_loads_that_skill(tmp_path: Path) -> None:
    write_skill(
        tmp_path,
        "frontend-design",
        "Create beautiful production web UI, landing pages, HTML, and CSS.",
    )
    write_skill(
        tmp_path,
        "frontend-slides",
        "Create polished frontend presentation slides and pitch decks.",
    )
    manager = SkillManager([tmp_path])
    manager.discover()

    matches = manager.suggest_skill_matches(
        "use frontend design skill and create a landing page about an AI meeting assistant",
        limit=3,
    )

    assert [match.skill.name for match in matches] == ["frontend-design"]
    assert matches[0].explicit is True
    assert matches[0].reason == "explicit skill name"


def test_inferred_frontend_landing_page_prefers_design_not_slides(tmp_path: Path) -> None:
    write_skill(
        tmp_path,
        "frontend-design",
        "Create beautiful production web UI, landing pages, HTML, and CSS.",
    )
    write_skill(
        tmp_path,
        "frontend-slides",
        "Create polished frontend presentation slides and pitch decks.",
    )
    manager = SkillManager([tmp_path])
    manager.discover()

    matches = manager.suggest_skill_matches(
        "create a beautiful landing page using html css about ai meeting assistant",
        limit=3,
    )

    assert [match.skill.name for match in matches] == ["frontend-design"]
    assert matches[0].explicit is False


def test_inferred_slide_request_prefers_frontend_slides(tmp_path: Path) -> None:
    write_skill(
        tmp_path,
        "frontend-design",
        "Create beautiful production web UI, landing pages, HTML, and CSS.",
    )
    write_skill(
        tmp_path,
        "frontend-slides",
        "Create polished frontend presentation slides and pitch decks.",
    )
    manager = SkillManager([tmp_path])
    manager.discover()

    matches = manager.suggest_skill_matches(
        "make presentation slides for this frontend product concept",
        limit=3,
    )

    assert [match.skill.name for match in matches] == ["frontend-slides"]


def test_named_skill_token_can_select_unique_matching_skill(tmp_path: Path) -> None:
    write_skill(
        tmp_path,
        "scientific-brainstorming",
        "Creative research ideation and exploration.",
    )
    write_skill(
        tmp_path,
        "frontend-design",
        "Create beautiful production web UI, landing pages, HTML, and CSS.",
    )
    manager = SkillManager([tmp_path])
    manager.discover()

    matches = manager.suggest_skill_matches(
        "use brainstorming skill and give me new ideas to create agents",
        limit=3,
    )

    assert [match.skill.name for match in matches] == ["scientific-brainstorming"]
    assert matches[0].explicit is True
    assert matches[0].reason == "named skill token"


def test_skill_aliases_are_used_for_explicit_matching(tmp_path: Path) -> None:
    write_skill_with_frontmatter(
        tmp_path,
        "scientific-brainstorming",
        [
            "name: scientific-brainstorming",
            "description: Creative research ideation and exploration.",
            "aliases: brainstorming, ideation",
        ],
    )
    manager = SkillManager([tmp_path])
    manager.discover()

    matches = manager.suggest_skill_matches(
        "use ideation skill to generate agent ideas",
        limit=3,
    )

    assert [match.skill.name for match in matches] == ["scientific-brainstorming"]
    assert matches[0].explicit is True
    assert matches[0].reason == "explicit skill name"


def test_discovery_supports_nested_skill_folders_and_allowed_tools_key(tmp_path: Path) -> None:
    skill_dir = tmp_path / "bundle" / "nested-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: nested-skill",
                "description: A nested skill.",
                "allowed-tools: read_file, apply_patch",
                "---",
                "",
                "# Nested Skill",
            ]
        ),
        encoding="utf-8",
    )
    manager = SkillManager([tmp_path])
    manager.discover()

    skill = manager.get_skill("nested-skill")

    assert skill.path == skill_dir / "SKILL.md"
    assert skill.allowed_tools == ["read_file", "apply_patch"]
