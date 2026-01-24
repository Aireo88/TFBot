import os
import json
import importlib.util
import logging
from pathlib import Path
from typing import Optional, Dict, Set, List

logger = logging.getLogger("tfbot")

# Bot name from environment, defaults to "Syn" for backwards compatibility
# Handle TEST_MODE logic similar to get_setting() in utils.py
def _get_bot_name() -> str:
    """Get bot name with TEST_MODE support (backward compatible)."""
    test_mode_raw = os.getenv("TFBOT_TEST", "").strip().upper()
    test_mode: Optional[bool] = None
    if test_mode_raw in ("YES", "TRUE", "1", "ON"):
        test_mode = True
    elif test_mode_raw in ("NO", "FALSE", "0", "OFF"):
        test_mode = False
    
    if test_mode is None:
        # Backward compatible: use base name
        return os.getenv("TFBOT_NAME", "Syn").strip() or "Syn"
    elif test_mode:
        # TEST mode: Use _TEST suffix, fallback to base name
        return os.getenv("TFBOT_NAME_TEST", os.getenv("TFBOT_NAME", "Syn")).strip() or "Syn"
    else:
        # LIVE mode: Use _LIVE suffix, fallback to base name
        return os.getenv("TFBOT_NAME_LIVE", os.getenv("TFBOT_NAME", "Syn")).strip() or "Syn"

BOT_NAME = _get_bot_name()

# Helper function to replace bot name placeholder in messages
def _format_message(message: str) -> str:
    """Replace {BOT_NAME} placeholder with actual bot name."""
    return message.replace("{BOT_NAME}", BOT_NAME)

_MODULE_DIR = Path(__file__).resolve().parent


def _resolve_characters_repo_root() -> Optional[Path]:
    """Locate the shared characters_repo directory (required)."""
    repo_dir_setting = os.getenv("TFBOT_CHARACTERS_REPO_DIR", "characters_repo").strip() or "characters_repo"
    repo_dir = Path(repo_dir_setting)
    if not repo_dir.is_absolute():
        repo_dir = (_MODULE_DIR / repo_dir).resolve()
    return repo_dir if repo_dir.exists() else None


_CHARACTERS_REPO_ROOT = _resolve_characters_repo_root()
if _CHARACTERS_REPO_ROOT is None:
    message = (
        "characters_repo directory not found. Ensure the shared repository exists "
        "and TFBOT_CHARACTERS_REPO_DIR points to it."
    )
    logger.critical(message)
    raise SystemExit(message)

_config_path = _CHARACTERS_REPO_ROOT / "tf_characters.json"
_packs_dir = _CHARACTERS_REPO_ROOT / "packs"

if _config_path.exists():
    logger.info("Character pack configuration: %s", _config_path)
else:
    logger.warning("Character pack configuration missing at %s", _config_path)

if _packs_dir.exists():
    logger.info("Character packs directory: %s", _packs_dir)
else:
    logger.warning("Character packs directory missing at %s", _packs_dir)

# Shared cache for loaded characters so repeated imports don't reprocess packs
_PACK_CACHE_KEY = f"tf_characters::{BOT_NAME}"
TF_CHARACTERS: list[dict] = []

if _PACK_CACHE_KEY in globals():
    cached_chars = globals().get(_PACK_CACHE_KEY)
    if isinstance(cached_chars, list) and cached_chars:
        TF_CHARACTERS = cached_chars.copy()
else:
    globals()[_PACK_CACHE_KEY] = TF_CHARACTERS

configured_files = set()

# Character-to-pack mappings for game filtering
_PACK_TO_CHARACTERS: Dict[str, Set[str]] = {}  # pack_name -> set of character names
_CHARACTER_TO_PACK: Dict[str, str] = {}  # character name -> pack_name


def _discover_available_games() -> Set[str]:
    """
    Discover available game types by scanning games/configs/ directory.
    Returns set of game_type strings (filename without .json extension).
    """
    games_dir = _MODULE_DIR.parent / "games" / "configs"
    if not games_dir.exists():
        logger.debug("Games configs directory not found: %s", games_dir)
        return set()
    
    game_types = set()
    for config_file in games_dir.glob("*.json"):
        game_type = config_file.stem  # filename without .json extension
        game_types.add(game_type)
        logger.debug("Discovered game type: %s", game_type)
    
    return game_types


def _ensure_config_option() -> None:
    """Ensure always_grab_faces_in_gameboard config option exists in tf_characters.json."""
    if not _config_path.exists():
        # Create new config file with default structure
        default_config = {
            "always_grab_faces_in_gameboard": True,
            "packs": []
        }
        try:
            with open(_config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            logger.info("Created new tf_characters.json with default config")
        except Exception as exc:
            logger.warning("Failed to create tf_characters.json: %s", exc)
        return
    
    try:
        with open(_config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # Check if config option exists
        needs_update = False
        
        if isinstance(config_data, list):
            # File is a list - convert to object structure
            config_data = {
                "always_grab_faces_in_gameboard": True,
                "packs": config_data
            }
            needs_update = True
            logger.info("Converting tf_characters.json from list to object structure")
        elif isinstance(config_data, dict):
            # File is already an object - just add the config option if missing
            if "always_grab_faces_in_gameboard" not in config_data:
                config_data["always_grab_faces_in_gameboard"] = True
                needs_update = True
                logger.info("Adding always_grab_faces_in_gameboard config option to tf_characters.json")
        
        # Write back if updated
        if needs_update:
            with open(_config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            logger.info("Updated tf_characters.json with always_grab_faces_in_gameboard config")
    except Exception as exc:
        logger.warning("Failed to ensure config option in tf_characters.json: %s", exc)


# Ensure config option exists before loading
_ensure_config_option()

if _config_path.exists():
    try:
        with open(_config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # Handle both list format (legacy) and object format (new)
        if isinstance(config_data, list):
            pack_configs = config_data
            logger.debug("Loaded tf_characters.json as list format (legacy)")
        elif isinstance(config_data, dict):
            pack_configs = config_data.get("packs", [])
            if not isinstance(pack_configs, list):
                logger.error("tf_characters.json 'packs' key is not a list, got %s. Falling back to empty list.", type(pack_configs))
                pack_configs = []
            else:
                logger.debug("Loaded tf_characters.json as object format (new), extracted %d packs from 'packs' key", len(pack_configs))
        else:
            logger.error("Unexpected tf_characters.json format, expected list or dict, got %s. Falling back to empty list.", type(config_data))
            pack_configs = []
        
        if not pack_configs:
            logger.warning("No pack configs found in tf_characters.json! Characters will not be loaded.")
        else:
            logger.info("Loading character packs for bot: %s (found %d pack configs)", BOT_NAME, len(pack_configs))
        
        # Discover available games for validation
        available_games = _discover_available_games()
        
        # Load enabled packs based on bot name
        for pack_config in pack_configs:
            if not isinstance(pack_config, dict):
                continue  # Skip non-dict entries
            pack_name = pack_config.get("name", "Unknown")
            pack_file = pack_config.get("file")
            enable_BunniBot = pack_config.get("enable_BunniBot", False)
            enable_VNBot = pack_config.get("enable_VNBot", False)
            
            if pack_file:
                configured_files.add(pack_file)
            
            # Check if pack is enabled for current bot
            should_load = False
            if BOT_NAME == "BunniBot" and enable_BunniBot:
                should_load = True
            elif BOT_NAME == "VNBot" and enable_VNBot:
                should_load = True
            
            # Log pack status
            status = "ENABLED" if should_load else "DISABLED"
            logger.info("  Pack '%s' (%s): %s", pack_name, pack_file, status)
            
            # Validate game flags (warn about unknown games, but don't fail)
            if available_games:
                for key in pack_config.keys():
                    if key.startswith("enable_") and "_" in key:
                        # Check if it's a game flag (enable_<bot>_<game>)
                        parts = key.split("_", 2)  # Split into ["enable", "BunniBot", "snakes_ladders"]
                        if len(parts) == 3:
                            game_type = parts[2]
                            if game_type not in available_games:
                                logger.warning("  Pack '%s' has game flag for unknown game: %s (key: %s)", 
                                             pack_name, game_type, key)
            
            if should_load and pack_file:
                if not _packs_dir.exists():
                    logger.warning("    Packs directory missing; cannot load %s.", pack_file)
                    continue

                # Try to load from packs directory
                pack_path = _packs_dir / f"{pack_file}.py"
                if pack_path.exists():
                    try:
                        spec = importlib.util.spec_from_file_location(pack_file, pack_path)
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(module)
                            pack_chars = getattr(module, "TF_CHARACTERS", None)
                            if isinstance(pack_chars, list):
                                # Track character-to-pack mapping
                                if pack_file not in _PACK_TO_CHARACTERS:
                                    _PACK_TO_CHARACTERS[pack_file] = set()
                                
                                for char in pack_chars:
                                    # Add _pack_name metadata to character dict
                                    if isinstance(char, dict):
                                        char["_pack_name"] = pack_file
                                        char_name = char.get("name", "").strip()
                                        if char_name:
                                            _PACK_TO_CHARACTERS[pack_file].add(char_name)
                                            _CHARACTER_TO_PACK[char_name] = pack_file
                                
                                TF_CHARACTERS.extend(pack_chars)
                                logger.info("    Loaded %d characters from %s", len(pack_chars), pack_file)
                    except Exception as exc:
                        logger.warning("Failed to load pack %s: %s", pack_file, exc)
                else:
                    # Try JSON file for Inanimate
                    pack_json_path = _packs_dir / f"{pack_file}.json"
                    if pack_json_path.exists():
                        try:
                            with open(pack_json_path, 'r', encoding='utf-8') as f:
                                pack_chars = json.load(f)
                                if isinstance(pack_chars, list):
                                    # Track character-to-pack mapping
                                    if pack_file not in _PACK_TO_CHARACTERS:
                                        _PACK_TO_CHARACTERS[pack_file] = set()
                                    
                                    for char in pack_chars:
                                        # Add _pack_name metadata to character dict
                                        if isinstance(char, dict):
                                            char["_pack_name"] = pack_file
                                            char_name = char.get("name", "").strip()
                                            if char_name:
                                                _PACK_TO_CHARACTERS[pack_file].add(char_name)
                                                _CHARACTER_TO_PACK[char_name] = pack_file
                                    
                                    TF_CHARACTERS.extend(pack_chars)
                                    logger.info("    Loaded %d characters from %s", len(pack_chars), pack_file)
                        except Exception as exc:
                            logger.warning("Failed to load pack %s: %s", pack_file, exc)
                    else:
                        logger.warning("Pack file %s not found in %s", pack_file, _packs_dir)
    except Exception as exc:
        logger.warning("Failed to load pack config from tf_characters.json: %s", exc)

# Auto-detect new pack files not in config
if _packs_dir.exists():
    detected_new_packs = []
    for filename in os.listdir(_packs_dir):
        if filename.startswith("characters_") and (filename.endswith(".py") or filename.endswith(".json")):
            pack_name = filename.replace(".py", "").replace(".json", "")
            if pack_name not in configured_files:
                detected_new_packs.append(pack_name)
    
    if detected_new_packs:
        logger.info("Detected %d new pack file(s) not in config (disabled by default):", len(detected_new_packs))
        for pack_name in detected_new_packs:
            logger.info("  - %s (add to tf_characters.json to enable)", pack_name)
    else:
        logger.info("No new pack files detected")

logger.info("Total characters loaded: %d", len(TF_CHARACTERS))


def get_enabled_packs_for_game(game_type: str, bot_name: str) -> Set[str]:
    """
    Get set of pack names enabled for a specific game and bot.
    Only used in gameboard mode - VN mode uses bot flags only.
    
    Args:
        game_type: Game type identifier (e.g., "snakes_ladders")
        bot_name: Bot name ("BunniBot" or "VNBot")
    
    Returns:
        Set of pack file names (not pack display names) that are enabled
    """
    if not _config_path.exists():
        return set()
    
    try:
        with open(_config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # Handle both list format (legacy) and object format (new)
        if isinstance(config_data, list):
            pack_configs = config_data
            logger.debug("get_enabled_packs_for_game: Loaded config as list format (legacy)")
        elif isinstance(config_data, dict):
            pack_configs = config_data.get("packs", [])
            if not isinstance(pack_configs, list):
                logger.error("get_enabled_packs_for_game: 'packs' key is not a list, got %s", type(pack_configs))
                pack_configs = []
            else:
                logger.debug("get_enabled_packs_for_game: Loaded config as object format (new), extracted %d packs", len(pack_configs))
        else:
            logger.error("get_enabled_packs_for_game: Unexpected format, expected list or dict, got %s", type(config_data))
            pack_configs = []
    except Exception as exc:
        logger.warning("Failed to load pack config for game filtering: %s", exc)
        return set()
    
    enabled_packs = set()
    game_flag_key = f"enable_{bot_name}_{game_type}"
    
    for pack_config in pack_configs:
        if not isinstance(pack_config, dict):
            continue  # Skip non-dict entries
        pack_file = pack_config.get("file")
        if not pack_file:
            continue
        
        # Check bot-specific game flag
        game_flag = pack_config.get(game_flag_key)
        
        # Only use game-specific flag - no fallback to bot flag
        # This ensures VN and gameboard pack settings are completely separate
        if game_flag is True:
            enabled_packs.add(pack_file)
        # If game_flag is False or None, pack is not enabled for this game
    
    # Log enabled packs at initialization (only if packs found)
    if enabled_packs:
        logger.info("Enabled packs for game %s/%s: %s", bot_name, game_type, sorted(enabled_packs))
    
    return enabled_packs


def get_filtered_characters_for_game(game_type: str, bot_name: str, enabled_packs: Optional[Set[str]] = None) -> List[dict]:
    """
    Get filtered TF_CHARACTERS list containing only characters from packs enabled for the game.
    Only used in gameboard mode - VN mode uses global TF_CHARACTERS.
    
    Args:
        game_type: Game type identifier (e.g., "snakes_ladders")
        bot_name: Bot name ("BunniBot" or "VNBot")
        enabled_packs: Optional set of pack names to use (if provided, skips reading config)
    
    Returns:
        Filtered list of character dicts
    """
    # If enabled_packs provided, use it directly (from saved game state)
    if enabled_packs is not None:
        filtered_chars = []
        for char in TF_CHARACTERS:
            if isinstance(char, dict):
                pack_name = char.get("_pack_name")
                if pack_name and pack_name in enabled_packs:
                    filtered_chars.append(char)
        logger.debug("Filtered %d characters for game %s using saved enabled_packs (from %d total)", 
                     len(filtered_chars), game_type, len(TF_CHARACTERS))
        return filtered_chars
    
    # Otherwise, read from config (for new games or backward compatibility)
    enabled_packs = get_enabled_packs_for_game(game_type, bot_name)
    
    if not enabled_packs:
        logger.debug("No packs enabled for game %s and bot %s", game_type, bot_name)
        return []
    
    filtered_chars = []
    for char in TF_CHARACTERS:
        if isinstance(char, dict):
            pack_name = char.get("_pack_name")
            if pack_name and pack_name in enabled_packs:
                filtered_chars.append(char)
    
    logger.debug("Filtered %d characters for game %s and bot %s (from %d total)", 
                 len(filtered_chars), game_type, bot_name, len(TF_CHARACTERS))
    return filtered_chars


def is_character_enabled_for_game(character_name: str, game_type: str, bot_name: str) -> bool:
    """
    Check if a specific character is enabled for a game.
    Only used in gameboard mode - VN mode uses bot flags only.
    
    Args:
        character_name: Character name to check
        game_type: Game type identifier (e.g., "snakes_ladders")
        bot_name: Bot name ("BunniBot" or "VNBot")
    
    Returns:
        True if character is enabled for the game, False otherwise
    """
    pack_name = _CHARACTER_TO_PACK.get(character_name)
    if not pack_name:
        return False
    
    enabled_packs = get_enabled_packs_for_game(game_type, bot_name)
    return pack_name in enabled_packs
