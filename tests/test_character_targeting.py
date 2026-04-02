import os
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

os.environ["TFBOT_CHARACTERS_REPO"] = ""
os.environ["TFBOT_CHANNEL_ID"] = "1"
os.environ["TFBOT_CHANNEL_ID_LIVE"] = "1"
os.environ["TFBOT_CHANNEL_ID_TEST"] = "1"
os.environ.setdefault("DISCORD_TOKEN", "test-token")

import bot
from tfbot.models import TransformationState


@dataclass
class _FakeMember:
    id: int
    display_name: str
    name: str


class _FakeGuild:
    def __init__(self, guild_id: int, members: list[_FakeMember]):
        self.id = guild_id
        self._members = {member.id: member for member in members}

    def get_member(self, user_id: int):
        return self._members.get(user_id)


class CharacterTargetingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._active_backup = dict(bot.active_transformations)
        self._overlay_backup = dict(bot.overlay_records)
        bot.active_transformations.clear()
        bot.overlay_records.clear()

    def tearDown(self) -> None:
        bot.active_transformations.clear()
        bot.active_transformations.update(self._active_backup)
        bot.overlay_records.clear()
        bot.overlay_records.update(self._overlay_backup)

    def _make_state(self, user_id: int, character_key: str) -> TransformationState:
        character = bot.CHARACTER_BY_NAME[character_key]
        now = datetime.now(timezone.utc)
        return TransformationState(
            user_id=user_id,
            guild_id=4242,
            character_name=character.name,
            character_avatar_path=character.avatar_path,
            character_message=character.message,
            original_nick=None,
            started_at=now,
            expires_at=now + timedelta(hours=1),
            duration_label="1 hour",
            character_folder=character.folder,
        )

    def test_forced_character_lookup_keeps_kiyoshi_distinct_from_kiyo(self) -> None:
        self.assertEqual(bot._find_character_by_token("kiyoshi").name, "Kiyoshi Honda")
        self.assertEqual(bot._find_character_by_token("kiyo").name, "Kiyo Honda")

    def test_forced_character_lookup_prefers_exact_folder_match_for_katrina(self) -> None:
        self.assertEqual(bot._find_character_by_token("katrina").name, "Katrina Morgan")
        self.assertIsNone(bot._find_character_by_token("kat"))

    def test_active_state_lookup_keeps_kiyoshi_distinct_from_kiyo(self) -> None:
        kiyo_state = self._make_state(101, "kiyo honda")
        kiyoshi_state = self._make_state(102, "kiyoshi honda")
        bot.active_transformations[bot.state_key(4242, 101)] = kiyo_state
        bot.active_transformations[bot.state_key(4242, 102)] = kiyoshi_state
        guild = _FakeGuild(
            4242,
            [
                _FakeMember(101, "User One", "userone"),
                _FakeMember(102, "User Two", "usertwo"),
            ],
        )

        self.assertIs(bot._find_state_by_token(guild, "kiyo"), kiyo_state)
        self.assertIs(bot._find_state_by_token(guild, "kiyoshi"), kiyoshi_state)

    def test_active_state_lookup_accepts_folder_basename(self) -> None:
        john_fem_state = self._make_state(103, "john fem (katrina's notebook)")
        bot.active_transformations[bot.state_key(4242, 103)] = john_fem_state
        guild = _FakeGuild(4242, [_FakeMember(103, "User Three", "userthree")])

        self.assertIs(bot._find_state_by_token(guild, "johnfem"), john_fem_state)

    def test_character_autocomplete_returns_real_folder_tokens(self) -> None:
        kiyoshi_matches = bot._autocomplete_character_names("kiyoshi", None)
        katrina_matches = bot._autocomplete_character_names("katrina", None)

        self.assertTrue(
            any(value == "kiyoshi" for _label, value in kiyoshi_matches)
        )
        self.assertTrue(
            any(value == "katrina" for _label, value in katrina_matches)
        )
        self.assertFalse(
            any(value == "st_characters" for _label, value in kiyoshi_matches)
        )

    def test_active_character_autocomplete_lists_only_active_forms(self) -> None:
        john_fem_state = self._make_state(103, "john fem (katrina's notebook)")
        bot.active_transformations[bot.state_key(4242, 103)] = john_fem_state
        guild = _FakeGuild(4242, [_FakeMember(103, "User Three", "userthree")])

        matches = bot._autocomplete_active_character_names("johnfem", guild)

        self.assertIn(("johnfem", "johnfem"), matches)
        self.assertFalse(any(value == "kiyoshi" for _label, value in matches))


if __name__ == "__main__":
    unittest.main()
