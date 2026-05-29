from pathlib import Path

from config.config import Config
from prompts.system import get_system_prompt
from skills.manager import SkillMetadata


def test_inactive_skill_descriptions_are_not_in_system_prompt(tmp_path: Path) -> None:
    skills = [
        SkillMetadata(
            name="frontend-design",
            description="Create beautiful production web UI and landing pages.",
            path=tmp_path / "frontend-design" / "SKILL.md",
        ),
        SkillMetadata(
            name="api-design",
            description="Design stable API contracts and endpoint boundaries.",
            path=tmp_path / "api-design" / "SKILL.md",
        ),
    ]

    prompt = get_system_prompt(
        config=Config(cwd=tmp_path),
        tools=[],
        skills=skills,
        active_skills=[],
        active_skill_bodies={},
    )

    assert "2 skill(s) are available in the local skill index" in prompt
    assert "Active skills: none" in prompt
    assert "Create beautiful production web UI" not in prompt
    assert "Design stable API contracts" not in prompt
    assert "frontend-design:" not in prompt
    assert "api-design:" not in prompt


def test_active_skill_body_is_disclosed_to_system_prompt(tmp_path: Path) -> None:
    skill_body = "# Frontend Design\n\nUse polished layout and responsive CSS."
    skills = [
        SkillMetadata(
            name="frontend-design",
            description="Create beautiful production web UI and landing pages.",
            path=tmp_path / "frontend-design" / "SKILL.md",
        )
    ]

    prompt = get_system_prompt(
        config=Config(cwd=tmp_path),
        tools=[],
        skills=skills,
        active_skills=["frontend-design"],
        active_skill_bodies={"frontend-design": skill_body},
    )

    assert "Active skills: frontend-design" in prompt
    assert "## frontend-design" in prompt
    assert skill_body in prompt
