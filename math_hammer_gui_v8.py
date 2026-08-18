import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import pandas as pd
import re
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
import math
import os

# ============================================================
# 40K 11TH EDITION MATHHAMMER
# - exact hit/wound/save probabilities
# - exact variable Attacks/Damage dice distributions
# - correct AP sign handling
# - correct Sustained/Lethal/Anti/Devastating interaction
# - 11th ed Heavy, Cover, Blast X and Cleave X handling
# - wargear selections modify the real equipped weapon counts
# ============================================================


# ============================================================
# 1. GENERIC HELPERS
# ============================================================

def clean_html(text: Any) -> str:
    if pd.isna(text) or text == '':
        return ''
    text = str(text)
    text = re.sub(r'<br\s*/?>', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&nbsp;', ' ')
    text = text.replace('•', '·')
    return re.sub(r'\s+', ' ', text).strip()


def parse_int(value: Any, default: int = 0) -> int:
    if pd.isna(value) or value in ('', '-', 'N/A'):
        return default
    match = re.search(r'-?\d+', str(value))
    return int(match.group(0)) if match else default


def parse_save_value(value: Any, default: int = 7) -> int:
    if pd.isna(value) or value in ('', '-', 'N/A'):
        return default
    match = re.search(r'\d+', str(value))
    return int(match.group(0)) if match else default


def parse_dice(value: Any) -> Tuple[int, int, int]:
    """Return (number_of_dice, sides, flat_modifier)."""
    if pd.isna(value):
        return (0, 0, 0)
    text = str(value).strip().upper().replace(' ', '')
    if text in ('', '-', 'N/A', '0'):
        return (0, 0, 0)
    if re.fullmatch(r'-?\d+', text):
        return (0, 0, int(text))
    match = re.fullmatch(r'(\d*)D(\d+)([+-]\d+)?', text)
    if match:
        return (
            int(match.group(1) or 1),
            int(match.group(2)),
            int(match.group(3) or 0),
        )
    # Last-resort fallback: treat the first integer as a flat value.
    match = re.search(r'-?\d+', text)
    return (0, 0, int(match.group(0))) if match else (0, 0, 0)


def dice_to_string(dice: Tuple[int, int, int]) -> str:
    n, sides, mod = dice
    if n <= 0 or sides <= 0:
        return str(mod)
    text = f"{'' if n == 1 else n}D{sides}"
    if mod > 0:
        text += f"+{mod}"
    elif mod < 0:
        text += str(mod)
    return text


def convolve_distributions(a: Dict[int, float], b: Dict[int, float]) -> Dict[int, float]:
    out: Dict[int, float] = defaultdict(float)
    for va, pa in a.items():
        for vb, pb in b.items():
            out[va + vb] += pa * pb
    return dict(out)


def dice_distribution(dice: Tuple[int, int, int], extra: int = 0) -> Dict[int, float]:
    n, sides, mod = dice
    if n <= 0 or sides <= 0:
        return {max(0, mod + extra): 1.0}
    dist: Dict[int, float] = {0: 1.0}
    one_die = {face: 1.0 / sides for face in range(1, sides + 1)}
    for _ in range(n):
        dist = convolve_distributions(dist, one_die)
    result: Dict[int, float] = defaultdict(float)
    for value, prob in dist.items():
        result[max(0, value + mod + extra)] += prob
    return dict(result)


def average_distribution(dist: Dict[int, float]) -> float:
    return sum(value * prob for value, prob in dist.items())


def clamp_modifier(value: int) -> int:
    """Hit/wound modifiers are capped at +/-1 in the core attack sequence."""
    return max(-1, min(1, value))


def keyword_key(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


def canonical_equipment_name(text: str) -> str:
    text = clean_html(text).strip(' .;,:')
    text = re.sub(r'^(?:an?|the)\s+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^\d+\s*[x×]?\s+', '', text, flags=re.IGNORECASE)
    return text.strip(' .;,:')


# ============================================================
# 2. WEAPON KEYWORDS AND DATA CLASSES
# ============================================================

def parse_keywords(description: Any) -> Dict[str, Any]:
    text = clean_html(description).lower()
    kw: Dict[str, Any] = {}

    # Valued abilities. 11th edition Blast/Cleave can explicitly carry X.
    valued_patterns = {
        'rapid_fire': r'rapid\s+fire\s*\(?\s*(\d+)\s*\)?',
        'sustained_hits': r'sustained\s+hits\s*\(?\s*(\d+)\s*\)?',
        'melta': r'melta\s*\(?\s*(\d+)\s*\)?',
        'blast_x': r'blast\s*\(?\s*(\d+)\s*\)?',
        'cleave_x': r'cleave\s*\(?\s*(\d+)\s*\)?',
    }
    for key, pattern in valued_patterns.items():
        match = re.search(pattern, text)
        if match:
            kw[key] = int(match.group(1))

    if 'blast' in text:
        kw['blast'] = True
        kw.setdefault('blast_x', 1)
    if 'cleave' in text:
        kw['cleave'] = True
        kw.setdefault('cleave_x', 1)

    # Anti-X N+ => Critical Wound on an unmodified N+ against matching keyword.
    for match in re.finditer(r'anti[-\s]+([a-z0-9 -]+?)\s+(\d)\+', text):
        target = keyword_key(match.group(1))
        kw[f'anti_{target}'] = int(match.group(2))

    bool_flags = {
        'torrent': r'\btorrent\b',
        'twin_linked': r'\btwin[- ]linked\b',
        'heavy': r'\bheavy\b',
        'assault': r'\bassault\b',
        'pistol': r'\bpistol\b',
        'lance': r'\blance\b',
        'devastating_wounds': r'\bdevastating\s+wounds\b',
        'lethal_hits': r'\blethal\s+hits\b',
        'ignores_cover': r'\bignores\s+cover\b',
        'hazardous': r'\bhazardous\b',
        'psychic': r'\bpsychic\b',
        'indirect_fire': r'\bindirect\s+fire\b',
        'one_shot': r'\bone\s+shot\b',
        'extra_attacks': r'\bextra\s+attacks\b',
        'precision': r'\bprecision\b',
    }
    for key, pattern in bool_flags.items():
        if re.search(pattern, text):
            kw[key] = True
    return kw


@dataclass
class ModelStats:
    name: str
    movement: str
    toughness: int
    save: int
    invuln: Optional[int]
    wounds: int
    leadership: int
    oc: int

    @classmethod
    def from_row(cls, row: pd.Series) -> 'ModelStats':
        inv = parse_save_value(row.get('inv_sv'), 99)
        save = parse_save_value(row.get('Sv'), 7)
        return cls(
            name=str(row.get('name', '') or ''),
            movement=str(row.get('M', '') or ''),
            toughness=parse_int(row.get('T'), 4),
            save=save,
            invuln=inv if inv < 7 else None,
            wounds=parse_int(row.get('W'), 1),
            leadership=parse_save_value(row.get('Ld'), 7),
            oc=parse_int(row.get('OC'), 1),
        )


@dataclass
class Weapon:
    datasheet_id: str
    name: str
    weapon_type: str
    range: str
    attacks_dice: Tuple[int, int, int]
    bs_ws: int
    strength: int
    ap: int
    damage_dice: Tuple[int, int, int]
    keywords: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_melee(self) -> bool:
        return self.weapon_type.lower() == 'melee' or self.range.lower() == 'melee'

    def keyword_string(self) -> str:
        parts: List[str] = []
        if self.keywords.get('torrent'):
            parts.append('Torrent')
        if self.keywords.get('heavy'):
            parts.append('Heavy')
        if self.keywords.get('twin_linked'):
            parts.append('Twin-linked')
        if self.keywords.get('rapid_fire', 0):
            parts.append(f"Rapid Fire {self.keywords['rapid_fire']}")
        if self.keywords.get('blast'):
            parts.append(f"Blast {self.keywords.get('blast_x', 1)}")
        if self.keywords.get('cleave'):
            parts.append(f"Cleave {self.keywords.get('cleave_x', 1)}")
        if self.keywords.get('sustained_hits', 0):
            parts.append(f"Sustained Hits {self.keywords['sustained_hits']}")
        for flag, label in (
            ('lethal_hits', 'Lethal Hits'),
            ('devastating_wounds', 'Devastating Wounds'),
            ('lance', 'Lance'),
            ('ignores_cover', 'Ignores Cover'),
            ('pistol', 'Pistol'),
            ('hazardous', 'Hazardous'),
            ('extra_attacks', 'Extra Attacks'),
            ('precision', 'Precision'),
        ):
            if self.keywords.get(flag):
                parts.append(label)
        for key, value in self.keywords.items():
            if key.startswith('anti_'):
                parts.append(f"Anti-{key[5:].replace('_', ' ').title()} {value}+")
        return ', '.join(parts) if parts else 'None'

    def attack_distribution(self, target_size: int, half_range: bool) -> Dict[int, float]:
        extra = 0
        if half_range:
            extra += int(self.keywords.get('rapid_fire', 0))
        if self.keywords.get('blast'):
            extra += int(self.keywords.get('blast_x', 1)) * max(0, target_size // 5)
        if self.keywords.get('cleave'):
            extra += int(self.keywords.get('cleave_x', 1)) * max(0, target_size // 5)
        return dice_distribution(self.attacks_dice, extra)

    def damage_distribution(self, half_range: bool) -> Dict[int, float]:
        extra = int(self.keywords.get('melta', 0)) if half_range else 0
        return dice_distribution(self.damage_dice, extra)


@dataclass
class ModelEquipment:
    model_name: str
    weapons: List[str] = field(default_factory=list)
    wargear: List[str] = field(default_factory=list)

    def clone(self) -> 'ModelEquipment':
        return ModelEquipment(self.model_name, self.weapons.copy(), self.wargear.copy())


@dataclass
class UnitLoadout:
    unit_name: str
    models: List[ModelEquipment] = field(default_factory=list)

    @property
    def total_models(self) -> int:
        return len(self.models)

    def weapon_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = defaultdict(int)
        for model in self.models:
            for weapon in model.weapons:
                counts[weapon] += 1
        return dict(counts)

    def display_lines(self) -> List[str]:
        grouped: Dict[Tuple[str, Tuple[str, ...], Tuple[str, ...]], int] = defaultdict(int)
        for model in self.models:
            key = (model.model_name, tuple(sorted(model.weapons)), tuple(sorted(model.wargear)))
            grouped[key] += 1
        lines: List[str] = []
        for (model_name, weapons, wargear), count in grouped.items():
            equipment = list(weapons) + list(wargear)
            suffix = ': ' + ', '.join(equipment) if equipment else ''
            lines.append(f"{count}x {model_name}{suffix}")
        return lines


@dataclass
class WargearOption:
    id: int
    description: str
    option_type: str
    target_weapon: Optional[str]
    choices: List[str]
    choice_bundles: Dict[str, List[str]] = field(default_factory=dict)
    target_model_hint: Optional[str] = None
    max_per_unit: Optional[int] = None
    per_x_models: Optional[int] = None
    unlimited: bool = False
    enabled: bool = False
    selected_count: int = 0
    selected_choice: Optional[str] = None

    def max_allowed(self, unit_size: int) -> int:
        if self.unlimited:
            return max(1, unit_size)
        if self.per_x_models:
            return max(0, unit_size // self.per_x_models)
        if self.max_per_unit is not None:
            return max(1, self.max_per_unit)
        return 1


@dataclass
class UnitData:
    id: str
    name: str
    faction_id: str
    faction_name: str
    loadout_text: str
    composition: List[dict]
    models: List[ModelStats]
    keywords: List[str]
    abilities: List[dict]
    weapons: List[Weapon]
    options: List[WargearOption]


@dataclass
class AttackResult:
    weapon_name: str
    weapon_count: int
    defender_model: str
    defender_count: int
    avg_attacks: float
    hit_probability: float
    critical_hit_probability: float
    avg_hits: float
    wound_probability: float
    critical_wound_probability: float
    avg_wounds: float
    regular_failed_saves: float
    devastating_wounds: float
    avg_damage: float
    expected_kills: float
    kill_probability: float
    expected_remaining_wounds_on_current: float
    effective_damage_distribution: Dict[int, float]


# ============================================================
# 3. DATA LOADING
# ============================================================

FACTION_NAMES = {
    'AC': 'Adeptus Custodes', 'AdM': 'Adeptus Mechanicus', 'AE': 'Aeldari',
    'AM': 'Astra Militarum', 'AoI': 'Agents of the Imperium',
    'AS': 'Adepta Sororitas', 'CD': 'Chaos Daemons', 'CSM': 'Chaos Space Marines',
    'DG': 'Death Guard', 'DRU': 'Drukhari', 'EC': "Emperor's Children",
    'GC': 'Genestealer Cults', 'GK': 'Grey Knights', 'LoV': 'Leagues of Votann',
    'NEC': 'Necrons', 'ORK': 'Orks', 'QI': 'Questoris Imperialis',
    'QT': 'Chaos Knights', 'SM': 'Space Marines', 'TAU': "T'au Empire",
    'TL': 'Titan Legions', 'TS': 'Thousand Sons', 'TYR': 'Tyranids',
    'WE': 'World Eaters',
}

UNIT_KEYWORDS = [
    'Infantry', 'Vehicle', 'Monster', 'Walker', 'Flyer', 'Beast', 'Swarm',
    'Cavalry', 'Mounted', 'Dreadnought', 'Terminator', 'Jump Pack', 'Battlesuit',
    'Titanic', 'Character', 'Epic Hero', 'Battleline', 'Psyker', 'Grenades',
    'Smoke', 'Transport', 'Dedicated Transport', 'Fortification', 'Fly', 'Aircraft',
    'Towering', 'Mobile',
]


def load_all_data(base_path: str = '.') -> Dict[str, pd.DataFrame]:
    filenames = {
        'units': 'Datasheets.csv',
        'wargear': 'Datasheets_wargear.csv',
        'composition': 'Datasheets_unit_composition.csv',
        'models': 'Datasheets_models.csv',
        'options': 'Datasheets_options.csv',
        'keywords': 'Datasheets_keywords.csv',
        'abilities': 'Datasheets_abilities.csv',
    }
    data: Dict[str, pd.DataFrame] = {}
    for key, filename in filenames.items():
        path = os.path.join(base_path, filename)
        if not os.path.exists(path):
            data[key] = pd.DataFrame()
            continue
        df = pd.read_csv(path, sep='|', dtype=str)
        df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
        data[key] = df
    return data


def parse_composition(df: pd.DataFrame, datasheet_id: str) -> List[dict]:
    if df.empty or 'datasheet_id' not in df.columns:
        return []
    rows = df[df['datasheet_id'] == datasheet_id]
    out: List[dict] = []
    for _, row in rows.iterrows():
        text = clean_html(row.get('description'))
        if not text or text.upper().startswith('OR'):
            continue
        match = re.match(r'^(\d+)\s*[-–]\s*(\d+)\s+(.+)$', text)
        if match:
            out.append({'name': match.group(3).strip(), 'min': int(match.group(1)), 'max': int(match.group(2))})
            continue
        match = re.match(r'^(\d+)\s+(.+)$', text)
        if match:
            n = int(match.group(1))
            out.append({'name': match.group(2).strip(), 'min': n, 'max': n})
            continue
        out.append({'name': text, 'min': 1, 'max': 1})
    return out


def get_models(df: pd.DataFrame, datasheet_id: str) -> List[ModelStats]:
    if df.empty or 'datasheet_id' not in df.columns:
        return []
    rows = df[df['datasheet_id'] == datasheet_id]
    return [ModelStats.from_row(row) for _, row in rows.iterrows()]


def get_keywords(df: pd.DataFrame, datasheet_id: str) -> List[str]:
    if df.empty or 'datasheet_id' not in df.columns:
        return []
    rows = df[df['datasheet_id'] == datasheet_id]
    values = []
    for _, row in rows.iterrows():
        value = clean_html(row.get('keyword'))
        if value:
            values.append(value)
    return sorted(set(values))


def get_abilities(df: pd.DataFrame, datasheet_id: str) -> List[dict]:
    if df.empty or 'datasheet_id' not in df.columns:
        return []
    rows = df[df['datasheet_id'] == datasheet_id]
    out = []
    for _, row in rows.iterrows():
        name = clean_html(row.get('name'))
        if name:
            out.append({'name': name, 'description': clean_html(row.get('description'))})
    return out


def parse_weapon(row: pd.Series) -> Weapon:
    return Weapon(
        datasheet_id=str(row.get('datasheet_id', '')),
        name=clean_html(row.get('name')),
        weapon_type=clean_html(row.get('type')) or 'Ranged',
        range=clean_html(row.get('range')) or 'Melee',
        attacks_dice=parse_dice(row.get('A')),
        bs_ws=parse_save_value(row.get('BS_WS'), 4),
        strength=parse_int(row.get('S'), 4),
        ap=parse_int(row.get('AP'), 0),
        damage_dice=parse_dice(row.get('D')),
        keywords=parse_keywords(row.get('description')),
    )


def get_weapons(df: pd.DataFrame, datasheet_id: str) -> List[Weapon]:
    if df.empty or 'datasheet_id' not in df.columns:
        return []
    rows = df[df['datasheet_id'] == datasheet_id]
    weapons = []
    for _, row in rows.iterrows():
        name = clean_html(row.get('name'))
        if not name:
            continue
        weapon = parse_weapon(row)
        if weapon.attacks_dice != (0, 0, 0):
            weapons.append(weapon)
    return weapons


def match_known_weapon(text: str, weapon_names: List[str]) -> Optional[str]:
    cleaned = canonical_equipment_name(text).lower()
    candidates = sorted(weapon_names, key=len, reverse=True)
    for name in candidates:
        n = name.lower()
        if cleaned == n:
            return name
    for name in candidates:
        n = name.lower()
        if re.search(rf'(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])', cleaned):
            return name
    return None


def find_known_weapons(text: str, weapon_names: List[str]) -> List[str]:
    low = clean_html(text).lower()
    found: List[Tuple[int, int, str]] = []
    for name in weapon_names:
        match = re.search(rf'(?<![a-z0-9]){re.escape(name.lower())}(?![a-z0-9])', low)
        if match:
            found.append((match.start(), -len(name), name))
    found.sort()
    result: List[str] = []
    for _, _, name in found:
        if name not in result:
            result.append(name)
    return result


def _choice_bundles(choice_text: str, weapon_names: List[str]) -> Dict[str, List[str]]:
    text = clean_html(choice_text).strip(' .:')
    # Wahapedia exports bullet alternatives with a bullet/marker. If bullets are not
    # present, a plain "or" is also treated as an alternative separator.
    if '·' in text:
        parts = [p.strip() for p in text.split('·') if p.strip()]
    elif re.search(r'\s+or\s+', text, re.IGNORECASE):
        parts = [p.strip() for p in re.split(r'\s+or\s+', text, flags=re.IGNORECASE) if p.strip()]
    else:
        parts = [text]

    bundles: Dict[str, List[str]] = {}
    for part in parts:
        found = find_known_weapons(part, weapon_names)
        if not found:
            continue
        label = ' + '.join(found)
        bundles[label] = found
    return bundles


def _model_hint_from_target_phrase(target_phrase: str, target_weapon: Optional[str]) -> Optional[str]:
    if not target_weapon:
        return None
    hint = clean_html(target_phrase)
    hint = re.sub(re.escape(target_weapon), ' ', hint, flags=re.IGNORECASE)
    hint = re.sub(r'^for every\s+\d+\s+models?\s+in\s+this\s+unit,?\s*\d*\s*', ' ', hint, flags=re.IGNORECASE)
    hint = re.sub(r'^up to\s+\d+\s+models?,?\s*', ' ', hint, flags=re.IGNORECASE)
    hint = re.sub(r'^\d+\s+', ' ', hint)
    hint = re.sub(r"[’']s\b", '', hint)
    hint = re.sub(r'\b(the|their|his|her|its|a|an|one|any|up to|model|models|each|can|have|has|in|this|unit)\b', ' ', hint, flags=re.IGNORECASE)
    hint = re.sub(r'\s+', ' ', hint).strip(' ,;:-')
    return hint or None


def _model_hint_from_add_subject(subject: str) -> Optional[str]:
    hint = clean_html(subject)
    hint = re.sub(r"[’']s\b", '', hint)
    hint = re.sub(r'\b(the|this|one|a|an|model|models|each|can|may)\b', ' ', hint, flags=re.IGNORECASE)
    hint = re.sub(r'\s+', ' ', hint).strip(' ,;:-')
    # Generic wording is not a useful model constraint.
    if not hint or hint.lower() in {'any number of', 'up to'}:
        return None
    if 'number of' in hint.lower():
        return None
    return hint


def parse_wargear_options(df: pd.DataFrame, datasheet_id: str, weapon_names: List[str]) -> List[WargearOption]:
    if df.empty or 'datasheet_id' not in df.columns:
        return []
    rows = df[df['datasheet_id'] == datasheet_id]
    result: List[WargearOption] = []

    for idx, (_, row) in enumerate(rows.iterrows()):
        desc = clean_html(row.get('description'))
        if not desc or desc.lower() in ('none', '-', 'or'):
            continue
        low = desc.lower()

        max_per_unit: Optional[int] = None
        per_x: Optional[int] = None
        unlimited = 'any number of models' in low or 'any number of model' in low

        match = re.search(r'for every\s+(\d+)\s+models?', low)
        if match:
            per_x = int(match.group(1))
        match = re.search(r'up to\s+(\d+)\s+models?', low)
        if match:
            max_per_unit = int(match.group(1))
        if max_per_unit is None:
            match = re.search(r'\b(\d+)\s+models?\b', low)
            if match and not per_x:
                max_per_unit = int(match.group(1))
        if max_per_unit is None and re.search(r'\bone model\b', low):
            max_per_unit = 1

        option_type = 'addition'
        target_weapon: Optional[str] = None
        target_model_hint: Optional[str] = None
        choice_text = desc

        rep = re.search(r'(?:have|has)\s+(?:their|its|his|her)\s+(.+?)\s+replaced\s+with\s+(.+)$', desc, re.IGNORECASE)
        if not rep:
            rep = re.search(r'(.+?)\s+can\s+(?:each\s+)?be\s+replaced\s+with\s+(.+)$', desc, re.IGNORECASE)
        if rep:
            option_type = 'replacement'
            target_phrase = rep.group(1)
            target_weapon = match_known_weapon(target_phrase, weapon_names)
            target_model_hint = _model_hint_from_target_phrase(target_phrase, target_weapon)
            choice_text = rep.group(2)
        else:
            add = re.search(r'(.+?)\s+(?:can|may)\s+(?:each\s+)?be\s+equipped\s+with\s+(.+)$', desc, re.IGNORECASE)
            if add:
                option_type = 'addition'
                target_model_hint = _model_hint_from_add_subject(add.group(1))
                choice_text = add.group(2)

        bundles = _choice_bundles(choice_text, weapon_names)

        # If exact parsing fails, expose each weapon mentioned after excluding the
        # replacement target. This is better than displaying a checkbox that has no
        # effect on the loadout.
        if not bundles:
            all_names = [n for n in find_known_weapons(desc, weapon_names) if n != target_weapon]
            for name in all_names:
                bundles[name] = [name]

        if not bundles:
            continue  # non-weapon wargear cannot affect attack math here

        choices = list(bundles.keys())
        option = WargearOption(
            id=idx,
            description=desc,
            option_type=option_type,
            target_weapon=target_weapon,
            choices=choices,
            choice_bundles=bundles,
            target_model_hint=target_model_hint,
            max_per_unit=max_per_unit,
            per_x_models=per_x,
            unlimited=unlimited,
        )
        option.selected_choice = choices[0]
        result.append(option)
    return result


def get_unit_data(data: Dict[str, pd.DataFrame], datasheet_id: str) -> Optional[UnitData]:
    units = data['units']
    if units.empty:
        return None
    rows = units[units['id'] == datasheet_id]
    if rows.empty:
        return None
    row = rows.iloc[0]
    faction_id = str(row.get('faction_id', '') or '')
    weapons = get_weapons(data['wargear'], datasheet_id)
    weapon_names = sorted(set(w.name for w in weapons))
    return UnitData(
        id=datasheet_id,
        name=clean_html(row.get('name')),
        faction_id=faction_id,
        faction_name=FACTION_NAMES.get(faction_id, faction_id),
        loadout_text=clean_html(row.get('loadout')),
        composition=parse_composition(data['composition'], datasheet_id),
        models=get_models(data['models'], datasheet_id),
        keywords=get_keywords(data['keywords'], datasheet_id),
        abilities=get_abilities(data['abilities'], datasheet_id),
        weapons=weapons,
        options=parse_wargear_options(data['options'], datasheet_id, weapon_names),
    )


# ============================================================
# 4. LOADOUT / WARGEAR ENGINE
# ============================================================

def build_model_names(unit: UnitData, requested_size: int) -> List[str]:
    requested_size = max(1, requested_size)
    if not unit.composition:
        default_name = unit.models[0].name if unit.models else unit.name
        return [default_name] * requested_size

    names: List[str] = []
    # First satisfy minimum composition.
    for comp in unit.composition:
        for _ in range(max(0, comp.get('min', 0))):
            if len(names) < requested_size:
                names.append(comp['name'])
    # Then fill toward maximums.
    for comp in unit.composition:
        already = names.count(comp['name'])
        capacity = max(0, comp.get('max', already) - already)
        for _ in range(capacity):
            if len(names) < requested_size:
                names.append(comp['name'])
    # Last fallback if the requested GUI size exceeds the composition data.
    fallback = unit.composition[-1]['name'] if unit.composition else unit.name
    while len(names) < requested_size:
        names.append(fallback)
    return names[:requested_size]


def _equipment_list_weapons(equipment_text: str, weapon_names: List[str]) -> List[str]:
    result: List[str] = []
    for item in re.split(r';|·', equipment_text):
        item = item.strip(' .;,:')
        if not item:
            continue
        qty_match = re.match(r'^(\d+)\s+(.+)$', item)
        qty = int(qty_match.group(1)) if qty_match else 1
        name_text = qty_match.group(2) if qty_match else item
        matched = match_known_weapon(name_text, weapon_names)
        if matched:
            result.extend([matched] * qty)
    return result


def parse_base_equipment_rules(loadout_text: str, weapon_names: List[str]) -> List[Tuple[str, List[str]]]:
    """Parse datasheet default-equipment clauses as (scope, weapons).

    Examples handled:
      Every model is equipped with: storm bolter; power fist.
      This model is equipped with: Smite; force weapon.
      The Sergeant is additionally equipped with: plasma pistol.
    """
    text = clean_html(loadout_text)
    if not text:
        return []
    pattern = re.compile(
        r'([^.:]+?\b(?:is|are)\s+(?:additionally\s+)?equipped\s+with)\s*:\s*([^.]*)',
        re.IGNORECASE,
    )
    rules: List[Tuple[str, List[str]]] = []
    for match in pattern.finditer(text):
        scope = match.group(1)
        scope = re.sub(r'\b(?:is|are)\s+(?:additionally\s+)?equipped\s+with\b', '', scope, flags=re.IGNORECASE)
        scope = scope.strip(' ,;:')
        weapons = _equipment_list_weapons(match.group(2), weapon_names)
        if weapons:
            rules.append((scope, weapons))
    return rules


def _scope_matches_model(scope: str, model_name: str, unit_size: int) -> bool:
    s = scope.lower().strip()
    m = model_name.lower().strip()
    if 'every model' in s or 'all models' in s:
        return True
    if 'this model' in s:
        return True  # singular datasheets and model-specific records use this wording
    # Remove articles/possessives and generic filler, then match against model type.
    s = re.sub(r'^(?:the|one)\s+', '', s)
    s = re.sub(r"['’]s$", '', s)
    significant = [tok for tok in re.findall(r'[a-z0-9]+', s) if tok not in {'model', 'models'}]
    return bool(significant) and all(tok in m for tok in significant)


def parse_base_weapons(loadout_text: str, weapon_names: List[str]) -> List[str]:
    """Compatibility fallback for datasheets whose loadout wording is unusual."""
    rules = parse_base_equipment_rules(loadout_text, weapon_names)
    if rules:
        # Only return universally-scoped equipment here; build_loadout handles
        # model-specific clauses itself.
        universal: List[str] = []
        for scope, weapons in rules:
            if 'every model' in scope.lower() or 'this model' in scope.lower() or 'all models' in scope.lower():
                universal.extend(weapons)
        return universal
    text = clean_html(loadout_text)
    equipment = text.split(':', 1)[1] if ':' in text else text
    return _equipment_list_weapons(equipment, weapon_names)


def build_loadout(unit: UnitData, requested_size: int, options: List[WargearOption]) -> UnitLoadout:
    model_names = build_model_names(unit, requested_size)
    weapon_names = sorted(set(w.name for w in unit.weapons))
    equipment_rules = parse_base_equipment_rules(unit.loadout_text, weapon_names)
    if equipment_rules:
        models = [ModelEquipment(name, []) for name in model_names]
        for model in models:
            for scope, weapons in equipment_rules:
                if _scope_matches_model(scope, model.model_name, len(models)):
                    model.weapons.extend(weapons)
    else:
        base_weapons = parse_base_weapons(unit.loadout_text, weapon_names)
        models = [ModelEquipment(name, base_weapons.copy()) for name in model_names]

    for option in options:
        if not option.enabled or not option.selected_choice:
            continue
        count = max(1, option.selected_count)
        choice = option.selected_choice
        bundle = option.choice_bundles.get(choice, [choice])
        applied = 0

        def eligible(model: ModelEquipment) -> bool:
            if not option.target_model_hint:
                return True
            hint_tokens = re.findall(r'[a-z0-9]+', option.target_model_hint.lower())
            model_low = model.model_name.lower()
            return all(token in model_low for token in hint_tokens)

        if option.option_type == 'replacement' and option.target_weapon:
            # Apply only to eligible models that actually carry the replaced weapon.
            for model in models:
                if applied >= count:
                    break
                if eligible(model) and option.target_weapon in model.weapons:
                    model.weapons.remove(option.target_weapon)
                    model.weapons.extend(bundle)
                    applied += 1
        else:
            for model in models:
                if applied >= count:
                    break
                if eligible(model):
                    model.weapons.extend(bundle)
                    applied += 1

    return UnitLoadout(unit.name, models)


# ============================================================
# 5. EXACT ATTACK MATH
# ============================================================

def d6_final_face_distribution(success_fn, reroll_mode: str) -> Dict[int, float]:
    """Distribution of final unmodified D6 faces after one allowed reroll."""
    out: Dict[int, float] = defaultdict(float)
    for first in range(1, 7):
        p_first = 1.0 / 6.0
        reroll = reroll_mode == 'all' and not success_fn(first)
        reroll = reroll or (reroll_mode == 'ones' and first == 1)
        if reroll:
            for second in range(1, 7):
                out[second] += p_first / 6.0
        else:
            out[first] += p_first
    return dict(out)


def hit_success(face: int, target: int, modifier: int) -> bool:
    if face == 1:
        return False
    if face == 6:
        return True
    return face + modifier >= target


def base_wound_target(strength: int, toughness: int) -> int:
    if strength >= 2 * toughness:
        return 2
    if strength > toughness:
        return 3
    if strength == toughness:
        return 4
    if 2 * strength <= toughness:
        return 6
    return 5


def anti_critical_threshold(weapon: Weapon, defender_keywords: List[str]) -> int:
    defender_keys = {keyword_key(k) for k in defender_keywords}
    thresholds = []
    for key, value in weapon.keywords.items():
        if not key.startswith('anti_'):
            continue
        anti_key = key[5:]
        # Match exact keyword or a multi-word keyword that contains the relevant noun.
        if anti_key in defender_keys or any(anti_key == k or anti_key in k.split('_') for k in defender_keys):
            thresholds.append(int(value))
    return min(thresholds) if thresholds else 6


def wound_success(face: int, target: int, modifier: int, critical_on: int) -> bool:
    if face == 1:
        return False
    if face >= critical_on:
        return True
    if face == 6:
        return True
    return face + modifier >= target


def save_fail_probability(save: int, invuln: Optional[int], ap: int) -> float:
    # AP is stored as negative values in the Wahapedia export. 3+ with AP -2 => 5+.
    armour_needed = save - ap
    best_needed = armour_needed
    if invuln is not None:
        best_needed = min(best_needed, invuln)
    if best_needed <= 2:
        save_success = 5.0 / 6.0  # unmodified 1 still fails
    elif best_needed > 6:
        save_success = 0.0
    else:
        save_success = (7 - best_needed) / 6.0
    return 1.0 - save_success


def _binomial_distribution(n: int, p: float) -> Dict[int, float]:
    if n <= 0:
        return {0: 1.0}
    out: Dict[int, float] = {}
    for k in range(n + 1):
        out[k] = math.comb(n, k) * (p ** k) * ((1.0 - p) ** (n - k))
    return out


def _event_count_for_hit_scenario(normal_hits: int, lethal_auto_wounds: int,
                                  normal_hit_event_p: float, lethal_event_p: float) -> Dict[int, float]:
    dist = _binomial_distribution(normal_hits, normal_hit_event_p)
    if lethal_auto_wounds:
        lethal_dist = _binomial_distribution(lethal_auto_wounds, lethal_event_p)
        dist = convolve_distributions(dist, lethal_dist)
    return dist


def per_attack_outcomes(
    weapon: Weapon,
    defender: ModelStats,
    defender_keywords: List[str],
    cover: bool,
    moved_more_than_3: bool,
    charging: bool,
    hit_reroll: str,
    wound_reroll: str,
    sustained_override: int,
    lethal_override: bool,
) -> Dict[str, Any]:
    # 11th ed: Heavy gives +1 to Hit if the unit has not moved >3" (other Heavy
    # conditions are not represented in this GUI). Cover penalises ranged accuracy;
    # Ignores Cover removes that penalty.
    hit_modifier = 0
    if weapon.keywords.get('heavy') and not moved_more_than_3:
        hit_modifier += 1
    if cover and not weapon.is_melee and not weapon.keywords.get('ignores_cover'):
        hit_modifier -= 1
    hit_modifier = clamp_modifier(hit_modifier)

    sustained = max(int(weapon.keywords.get('sustained_hits', 0)), sustained_override)
    lethal = bool(weapon.keywords.get('lethal_hits')) or lethal_override

    wound_target = base_wound_target(weapon.strength, defender.toughness)
    wound_modifier = 1 if weapon.keywords.get('lance') and charging else 0
    wound_modifier = clamp_modifier(wound_modifier)
    critical_on = anti_critical_threshold(weapon, defender_keywords)

    effective_wound_reroll = 'all' if weapon.keywords.get('twin_linked') else wound_reroll
    wound_success_fn = lambda face: wound_success(face, wound_target, wound_modifier, critical_on)
    wound_faces = d6_final_face_distribution(wound_success_fn, effective_wound_reroll)
    p_wound_per_roll = sum(p for face, p in wound_faces.items() if wound_success_fn(face))
    p_crit_wound_per_roll = sum(
        p for face, p in wound_faces.items()
        if face >= critical_on and face != 1
    )

    fail_save = save_fail_probability(defender.save, defender.invuln, weapon.ap)
    devastating = bool(weapon.keywords.get('devastating_wounds'))
    if devastating:
        p_normal_hit_damage_event = (
            p_crit_wound_per_roll
            + max(0.0, p_wound_per_roll - p_crit_wound_per_roll) * fail_save
        )
        p_regular_failed_per_normal_hit = max(0.0, p_wound_per_roll - p_crit_wound_per_roll) * fail_save
        p_dev_per_normal_hit = p_crit_wound_per_roll
    else:
        p_normal_hit_damage_event = p_wound_per_roll * fail_save
        p_regular_failed_per_normal_hit = p_wound_per_roll * fail_save
        p_dev_per_normal_hit = 0.0

    # Build an exact distribution of the number of damaging wound-events generated
    # by ONE attack die. Sustained Hits can make this >1; Lethal Hits creates an
    # auto-wound from the original Critical Hit while the Sustained bonus hits still
    # roll to wound normally.
    event_count_dist: Dict[int, float] = defaultdict(float)
    expected_normal_hits = 0.0
    expected_lethal_auto = 0.0
    p_hit = 0.0
    p_crit_hit = 0.0

    if weapon.keywords.get('torrent'):
        hit_scenarios = [(1.0, 1, 0)]  # probability, normal hits, lethal autos
        p_hit = 1.0
    else:
        hit_success_fn = lambda face: hit_success(face, weapon.bs_ws, hit_modifier)
        hit_faces = d6_final_face_distribution(hit_success_fn, hit_reroll)
        hit_scenarios = []
        for face, probability in hit_faces.items():
            if not hit_success_fn(face):
                hit_scenarios.append((probability, 0, 0))
                continue
            p_hit += probability
            if face == 6:
                p_crit_hit += probability
                if lethal:
                    hit_scenarios.append((probability, sustained, 1))
                else:
                    hit_scenarios.append((probability, 1 + sustained, 0))
            else:
                hit_scenarios.append((probability, 1, 0))

    for scenario_prob, normal_hits, lethal_autos in hit_scenarios:
        expected_normal_hits += scenario_prob * normal_hits
        expected_lethal_auto += scenario_prob * lethal_autos
        scenario_events = _event_count_for_hit_scenario(
            normal_hits,
            lethal_autos,
            p_normal_hit_damage_event,
            fail_save,
        )
        for count, probability in scenario_events.items():
            event_count_dist[count] += scenario_prob * probability

    # Numerical cleanup.
    total = sum(event_count_dist.values())
    if total > 0:
        event_count_dist = {k: v / total for k, v in event_count_dist.items() if v > 1e-15}
    else:
        event_count_dist = {0: 1.0}

    expected_events = average_distribution(event_count_dist)
    expected_hits = expected_normal_hits + expected_lethal_auto
    expected_wounds = expected_normal_hits * p_wound_per_roll + expected_lethal_auto
    regular_failed = expected_normal_hits * p_regular_failed_per_normal_hit + expected_lethal_auto * fail_save
    devastating_events = expected_normal_hits * p_dev_per_normal_hit

    return {
        'p_hit': p_hit,
        'p_crit_hit': p_crit_hit,
        'expected_hits': expected_hits,
        'p_wound_per_roll': p_wound_per_roll,
        'p_crit_wound_per_roll': p_crit_wound_per_roll,
        'expected_wounds': expected_wounds,
        'regular_failed': regular_failed,
        'devastating': devastating_events,
        'event_count_dist': dict(event_count_dist),
        'expected_damaging_events': expected_events,
    }


def apply_one_damage_event_always(
    state_dist: Dict[Tuple[int, int], float],
    damage_dist: Dict[int, float],
    defender_count: int,
    wounds_per_model: int,
) -> Dict[Tuple[int, int], float]:
    out: Dict[Tuple[int, int], float] = defaultdict(float)
    for (kills, wounds_taken), state_prob in state_dist.items():
        if kills >= defender_count:
            out[(defender_count, 0)] += state_prob
            continue
        for damage, damage_prob in damage_dist.items():
            prob = state_prob * damage_prob
            if damage <= 0:
                out[(kills, wounds_taken)] += prob
                continue
            total = wounds_taken + damage
            if total >= wounds_per_model:
                new_kills = min(defender_count, kills + 1)
                # Normal/Devastating weapon damage is allocated to one model; excess
                # from that attack is discarded rather than spilling to the next model.
                out[(new_kills, 0)] += prob
            else:
                out[(kills, total)] += prob
    return dict(out)


def apply_one_attack(
    state_dist: Dict[Tuple[int, int], float],
    event_count_dist: Dict[int, float],
    damage_dist: Dict[int, float],
    defender_count: int,
    wounds_per_model: int,
) -> Dict[Tuple[int, int], float]:
    max_events = max(event_count_dist) if event_count_dist else 0
    after_k = dict(state_dist)
    mixed: Dict[Tuple[int, int], float] = defaultdict(float)
    for k in range(max_events + 1):
        weight = event_count_dist.get(k, 0.0)
        if weight:
            for state, probability in after_k.items():
                mixed[state] += weight * probability
        if k < max_events:
            after_k = apply_one_damage_event_always(
                after_k, damage_dist, defender_count, wounds_per_model
            )
    return dict(mixed)


def resolve_attack_count_mixture(
    initial_states: Dict[Tuple[int, int], float],
    attack_count_dist: Dict[int, float],
    event_count_dist: Dict[int, float],
    damage_dist: Dict[int, float],
    defender_count: int,
    wounds_per_model: int,
) -> Dict[Tuple[int, int], float]:
    max_attacks = max(attack_count_dist) if attack_count_dist else 0
    current = dict(initial_states)
    mixed: Dict[Tuple[int, int], float] = defaultdict(float)
    for attack_number in range(max_attacks + 1):
        weight = attack_count_dist.get(attack_number, 0.0)
        if weight:
            for state, prob in current.items():
                mixed[state] += weight * prob
        if attack_number < max_attacks:
            current = apply_one_attack(
                current, event_count_dist, damage_dist,
                defender_count, wounds_per_model
            )
    return dict(mixed)


def weapon_group_attack_distribution(weapon: Weapon, copies: int, target_size: int, half_range: bool) -> Dict[int, float]:
    one_copy = weapon.attack_distribution(target_size, half_range)
    total = {0: 1.0}
    for _ in range(max(0, copies)):
        total = convolve_distributions(total, one_copy)
    return total


def calculate_attack(
    weapon: Weapon,
    weapon_count: int,
    defender: ModelStats,
    defender_count: int,
    defender_keywords: List[str],
    half_range: bool = False,
    cover: bool = False,
    charging: bool = False,
    moved_more_than_3: bool = False,
    hit_reroll: str = 'none',
    wound_reroll: str = 'none',
    sustained_override: int = 0,
    lethal_override: bool = False,
) -> AttackResult:
    defender_count = max(1, defender_count)
    weapon_count = max(1, weapon_count)

    per_attack = per_attack_outcomes(
        weapon, defender, defender_keywords, cover, moved_more_than_3,
        charging, hit_reroll, wound_reroll, sustained_override, lethal_override,
    )
    attacks_dist = weapon_group_attack_distribution(weapon, weapon_count, defender_count, half_range)
    avg_attacks = average_distribution(attacks_dist)
    damage_dist = weapon.damage_distribution(half_range)
    avg_damage_per_event = average_distribution(damage_dist)

    # Exact defender-state distribution including variable attacks, variable damage,
    # overkill on multi-wound models, and finite target model count.
    states = resolve_attack_count_mixture(
        {(0, 0): 1.0},
        attacks_dist,
        per_attack['event_count_dist'],
        damage_dist,
        defender_count,
        max(1, defender.wounds),
    )

    expected_kills = sum(kills * prob for (kills, _), prob in states.items())
    kill_probability = sum(prob for (kills, _), prob in states.items() if kills >= 1)
    expected_wounds_current = sum(wounds * prob for (_, wounds), prob in states.items())
    effective_damage_dist: Dict[int, float] = defaultdict(float)
    for (kills, wounds), prob in states.items():
        effective = min(defender_count * defender.wounds, kills * defender.wounds + wounds)
        effective_damage_dist[effective] += prob

    return AttackResult(
        weapon_name=weapon.name,
        weapon_count=weapon_count,
        defender_model=defender.name,
        defender_count=defender_count,
        avg_attacks=avg_attacks,
        hit_probability=per_attack['p_hit'],
        critical_hit_probability=per_attack['p_crit_hit'],
        avg_hits=avg_attacks * per_attack['expected_hits'],
        wound_probability=per_attack['p_wound_per_roll'],
        critical_wound_probability=per_attack['p_crit_wound_per_roll'],
        avg_wounds=avg_attacks * per_attack['expected_wounds'],
        regular_failed_saves=avg_attacks * per_attack['regular_failed'],
        devastating_wounds=avg_attacks * per_attack['devastating'],
        avg_damage=avg_attacks * per_attack['expected_damaging_events'] * avg_damage_per_event,
        expected_kills=expected_kills,
        kill_probability=kill_probability,
        expected_remaining_wounds_on_current=expected_wounds_current,
        effective_damage_distribution=dict(effective_damage_dist),
    )


# ============================================================
# 6. GUI WIDGETS
# ============================================================

class WargearOptionWidget:
    def __init__(self, parent, option: WargearOption, unit_size: int, callback):
        self.option = option
        self.unit_size = unit_size
        self.callback = callback
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill=tk.X, padx=4, pady=3)

        self.enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.frame, variable=self.enabled, command=self.on_toggle).grid(row=0, column=0, sticky='nw')
        ttk.Label(self.frame, text=option.description, wraplength=430, justify=tk.LEFT).grid(row=0, column=1, columnspan=4, sticky='w')

        max_allowed = option.max_allowed(unit_size)
        ttk.Label(self.frame, text='Models:').grid(row=1, column=1, sticky='w', padx=(0, 4))
        self.count = ttk.Spinbox(self.frame, from_=1, to=max_allowed, width=4, state='disabled')
        self.count.set(1)
        self.count.grid(row=1, column=2, sticky='w')
        self.count.bind('<KeyRelease>', self.on_change)
        self.count.bind('<<Increment>>', self.on_change)
        self.count.bind('<<Decrement>>', self.on_change)

        ttk.Label(self.frame, text='Choice:').grid(row=1, column=3, sticky='w', padx=(10, 4))
        self.choice = ttk.Combobox(self.frame, values=option.choices, width=28, state='disabled')
        if option.choices:
            self.choice.current(0)
        self.choice.grid(row=1, column=4, sticky='we')
        self.choice.bind('<<ComboboxSelected>>', self.on_change)

        detail = 'replacement' if option.option_type == 'replacement' else 'addition'
        if option.target_weapon:
            detail += f"; replaces {option.target_weapon}"
        if option.target_model_hint:
            detail += f"; model {option.target_model_hint}"
        ttk.Label(self.frame, text=f"[{detail}; max {max_allowed}]", font=('', 8, 'italic')).grid(row=2, column=1, columnspan=4, sticky='w')
        self.frame.columnconfigure(4, weight=1)

    def on_toggle(self):
        enabled = self.enabled.get()
        self.count.config(state='normal' if enabled else 'disabled')
        self.choice.config(state='readonly' if enabled else 'disabled')
        self.option.enabled = enabled
        self.option.selected_count = int(self.count.get()) if enabled else 0
        self.option.selected_choice = self.choice.get() if enabled else None
        self.callback()

    def on_change(self, *_):
        if not self.enabled.get():
            return
        try:
            value = int(self.count.get())
        except ValueError:
            value = 1
        value = max(1, min(value, self.option.max_allowed(self.unit_size)))
        self.count.set(value)
        self.option.selected_count = value
        self.option.selected_choice = self.choice.get() or (self.option.choices[0] if self.option.choices else None)
        self.callback()


class LoadoutDisplayWidget:
    def __init__(self, parent):
        frame = ttk.LabelFrame(parent, text='Effective Unit Loadout', padding=5)
        frame.pack(fill=tk.BOTH, expand=False, pady=(5, 0))
        self.text = tk.Text(frame, height=7, wrap=tk.WORD, font=('Courier', 8))
        self.text.pack(fill=tk.BOTH, expand=True)

    def update(self, loadout: Optional[UnitLoadout]):
        self.text.delete('1.0', tk.END)
        if not loadout:
            self.text.insert(tk.END, 'No loadout')
            return
        lines = [f"{loadout.unit_name}: {loadout.total_models} models", ''] + loadout.display_lines()
        self.text.insert(tk.END, '\n'.join(lines))


# ============================================================
# 7. MAIN GUI
# ============================================================

class MathHammerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title('Warhammer 40,000 11th Edition MathHammer')
        self.root.geometry('1800x1000')

        self.data: Dict[str, pd.DataFrame] = {}
        self.units: List[UnitData] = []
        self.attacker: Optional[UnitData] = None
        self.defender: Optional[UnitData] = None
        self.defender_stats: Optional[ModelStats] = None
        self.current_loadout: Optional[UnitLoadout] = None
        self.wargear_widgets: List[WargearOptionWidget] = []
        self.weapon_groups: List[Tuple[Weapon, int]] = []
        self.last_result: Optional[AttackResult] = None

        self.create_ui()
        self.load_data()

    def create_ui(self):
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        left = ttk.Frame(paned)
        right = ttk.Frame(paned)
        paned.add(left, weight=1)
        paned.add(right, weight=2)

        self.create_selector(left, 'attacker', 'Attacker')
        self.create_selector(left, 'defender', 'Defender')

        mods = ttk.LabelFrame(right, text='Modifiers', padding=8)
        mods.pack(fill=tk.X)
        self.half_range = tk.BooleanVar()
        self.cover = tk.BooleanVar()
        self.charging = tk.BooleanVar()
        self.moved = tk.BooleanVar()
        self.lethal = tk.BooleanVar()
        ttk.Checkbutton(mods, text='Half Range', variable=self.half_range).grid(row=0, column=0, sticky='w', padx=4)
        ttk.Checkbutton(mods, text='Target in Cover (-1 accuracy)', variable=self.cover).grid(row=0, column=1, sticky='w', padx=4)
        ttk.Checkbutton(mods, text='Charging (Lance)', variable=self.charging).grid(row=0, column=2, sticky='w', padx=4)
        ttk.Checkbutton(mods, text='Moved >3" (disables Heavy bonus)', variable=self.moved).grid(row=0, column=3, sticky='w', padx=4)
        ttk.Checkbutton(mods, text='Add Lethal Hits', variable=self.lethal).grid(row=0, column=4, sticky='w', padx=4)

        ttk.Label(mods, text='Hit reroll:').grid(row=1, column=0, sticky='e')
        self.hit_reroll = tk.StringVar(value='none')
        ttk.Combobox(mods, values=['none', 'ones', 'all'], textvariable=self.hit_reroll, width=8, state='readonly').grid(row=1, column=1, sticky='w')
        ttk.Label(mods, text='Wound reroll:').grid(row=1, column=2, sticky='e')
        self.wound_reroll = tk.StringVar(value='none')
        ttk.Combobox(mods, values=['none', 'ones', 'all'], textvariable=self.wound_reroll, width=8, state='readonly').grid(row=1, column=3, sticky='w')
        ttk.Label(mods, text='Sustained Hits override:').grid(row=1, column=4, sticky='e')
        self.sustained = tk.IntVar(value=0)
        ttk.Spinbox(mods, from_=0, to=6, width=4, textvariable=self.sustained).grid(row=1, column=5, sticky='w')

        buttons = ttk.Frame(right)
        buttons.pack(fill=tk.X, pady=5)
        ttk.Button(buttons, text='⚔ CALCULATE', command=self.calculate).pack(side=tk.LEFT, padx=3)
        ttk.Button(buttons, text='📊 Compare Equipped Weapons', command=self.compare_weapons).pack(side=tk.LEFT, padx=3)
        ttk.Button(buttons, text='Clear', command=self.clear_results).pack(side=tk.LEFT, padx=3)
        ttk.Button(buttons, text='Export', command=self.export_results).pack(side=tk.LEFT, padx=3)

        result_frame = ttk.LabelFrame(right, text='Results', padding=5)
        result_frame.pack(fill=tk.BOTH, expand=True)
        self.result_text = scrolledtext.ScrolledText(result_frame, font=('Courier', 9))
        self.result_text.pack(fill=tk.BOTH, expand=True)

        self.status = tk.StringVar(value='Ready')
        ttk.Label(self.root, textvariable=self.status, relief=tk.SUNKEN, anchor='w').pack(fill=tk.X)

    def create_selector(self, parent, side: str, title: str):
        frame = ttk.LabelFrame(parent, text=title, padding=6)
        frame.pack(fill=tk.BOTH, expand=True, pady=4)

        filter_row = ttk.Frame(frame)
        filter_row.pack(fill=tk.X)
        ttk.Label(filter_row, text='Faction:').pack(side=tk.LEFT)
        faction = ttk.Combobox(filter_row, state='readonly', width=20)
        faction.pack(side=tk.LEFT, padx=3)
        setattr(self, f'{side}_faction', faction)
        faction.bind('<<ComboboxSelected>>', lambda e, s=side: self.filter_units(s))

        search = ttk.Entry(filter_row)
        search.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)
        setattr(self, f'{side}_search', search)
        search.bind('<KeyRelease>', lambda e, s=side: self.filter_units(s))

        listbox = tk.Listbox(frame, height=7, font=('Courier', 8))
        listbox.pack(fill=tk.BOTH, expand=True)
        setattr(self, f'{side}_listbox', listbox)
        listbox.bind('<<ListboxSelect>>', lambda e, s=side: self.on_unit_select(s))

        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X, pady=3)
        ttk.Label(controls, text='Count:').pack(side=tk.LEFT)
        count = ttk.Spinbox(controls, from_=1, to=40, width=4)
        count.set(5 if side == 'attacker' else 10)
        count.pack(side=tk.LEFT, padx=3)
        setattr(self, f'{side}_count', count)
        count.bind('<KeyRelease>', lambda e, s=side: self.on_count_change(s))

        if side == 'attacker':
            ttk.Label(controls, text='Equipped weapon:').pack(side=tk.LEFT, padx=(10, 3))
            weapon = ttk.Combobox(controls, state='readonly', width=32)
            weapon.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.attacker_weapon = weapon
            weapon.bind('<<ComboboxSelected>>', lambda e: self.update_weapon_stats())

        info = tk.Text(frame, height=5, wrap=tk.WORD, font=('Courier', 8))
        info.pack(fill=tk.X)
        setattr(self, f'{side}_info', info)

        if side == 'attacker':
            wg = ttk.LabelFrame(frame, text='Wargear Options (affects calculations)', padding=4)
            wg.pack(fill=tk.X, pady=4)
            canvas = tk.Canvas(wg, height=180)
            scrollbar = ttk.Scrollbar(wg, orient=tk.VERTICAL, command=canvas.yview)
            inner = ttk.Frame(canvas)
            inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
            canvas.create_window((0, 0), window=inner, anchor='nw')
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.wargear_inner = inner
            self.loadout_display = LoadoutDisplayWidget(frame)
            self.weapon_stats = tk.Text(frame, height=4, font=('Courier', 8))
            self.weapon_stats.pack(fill=tk.X, pady=(4, 0))

    def load_data(self):
        try:
            self.status.set('Loading CSV data...')
            self.data = load_all_data('.')
            self.units = []
            if self.data['units'].empty:
                raise RuntimeError('Datasheets.csv not found or empty')
            for _, row in self.data['units'].iterrows():
                datasheet_id = str(row.get('id', '') or '')
                if not datasheet_id:
                    continue
                try:
                    unit = get_unit_data(self.data, datasheet_id)
                    if unit:
                        self.units.append(unit)
                except Exception as exc:
                    print(f'Unit {datasheet_id} skipped: {exc}')
            factions = ['All Factions'] + sorted(set(u.faction_name for u in self.units))
            for side in ('attacker', 'defender'):
                combo = getattr(self, f'{side}_faction')
                combo['values'] = factions
                combo.current(0)
                self.filter_units(side)
            self.status.set(f'Loaded {len(self.units)} units')
        except Exception as exc:
            self.status.set(f'Load error: {exc}')
            messagebox.showerror('Load Error', str(exc))

    def filter_units(self, side: str):
        faction = getattr(self, f'{side}_faction').get()
        search = getattr(self, f'{side}_search').get().strip().lower()
        filtered = [
            u for u in self.units
            if (faction in ('', 'All Factions') or u.faction_name == faction)
            and (not search or search in u.name.lower())
        ]
        setattr(self, f'{side}_filtered', filtered)
        listbox = getattr(self, f'{side}_listbox')
        listbox.delete(0, tk.END)
        for unit in filtered[:200]:
            listbox.insert(tk.END, f'{unit.name} ({unit.faction_name})')

    def on_unit_select(self, side: str):
        listbox = getattr(self, f'{side}_listbox')
        if not listbox.curselection():
            return
        index = listbox.curselection()[0]
        filtered = getattr(self, f'{side}_filtered')
        if index >= len(filtered):
            return
        unit = filtered[index]
        if side == 'attacker':
            self.attacker = unit
            self.load_wargear_widgets()
            self.rebuild_loadout()
        else:
            self.defender = unit
            self.defender_stats = unit.models[0] if unit.models else None
        self.update_unit_info(side, unit)

    def update_unit_info(self, side: str, unit: UnitData):
        widget = getattr(self, f'{side}_info')
        widget.delete('1.0', tk.END)
        lines = [unit.name, f'Faction: {unit.faction_name}']
        if unit.models:
            m = unit.models[0]
            inv = f' Inv{m.invuln}+' if m.invuln else ''
            lines.append(f'T{m.toughness} Sv{m.save}+{inv} W{m.wounds} Ld{m.leadership}+ OC{m.oc}')
        if unit.keywords:
            lines.append('Keywords: ' + ', '.join(unit.keywords[:12]))
        if unit.loadout_text:
            lines.append('Base: ' + unit.loadout_text[:180])
        widget.insert(tk.END, '\n'.join(lines))

    def load_wargear_widgets(self):
        for child in self.wargear_inner.winfo_children():
            child.destroy()
        self.wargear_widgets = []
        if not self.attacker:
            return
        try:
            size = int(self.attacker_count.get())
        except ValueError:
            size = 5
        if not self.attacker.options:
            ttk.Label(self.wargear_inner, text='No weapon-changing wargear options parsed for this unit.').pack(anchor='w')
            return
        # Reset state when loading a unit / changing size.
        for option in self.attacker.options:
            if option.max_allowed(size) <= 0:
                continue
            option.enabled = False
            option.selected_count = 0
            option.selected_choice = option.choices[0] if option.choices else None
            widget = WargearOptionWidget(self.wargear_inner, option, size, self.rebuild_loadout)
            self.wargear_widgets.append(widget)

    def on_count_change(self, side: str):
        if side == 'attacker' and self.attacker:
            self.load_wargear_widgets()
            self.rebuild_loadout()

    def rebuild_loadout(self):
        if not self.attacker:
            return
        try:
            size = int(self.attacker_count.get())
        except ValueError:
            size = 5
        self.current_loadout = build_loadout(self.attacker, size, self.attacker.options)
        self.loadout_display.update(self.current_loadout)
        self.refresh_equipped_weapons()

    def refresh_equipped_weapons(self):
        if not self.attacker:
            self.weapon_groups = []
            self.attacker_weapon['values'] = []
            return
        counts = self.current_loadout.weapon_counts() if self.current_loadout else {}

        groups: List[Tuple[Weapon, int]] = []
        for weapon in self.attacker.weapons:
            count = counts.get(weapon.name, 0)
            if count > 0:
                groups.append((weapon, count))

        # If the textual base loadout cannot be parsed, keep the application useful:
        # expose all weapon profiles at unit-size count. Wargear additions/replacements
        # still take precedence whenever they produce a real loadout weapon count.
        if not groups:
            try:
                fallback_count = int(self.attacker_count.get())
            except ValueError:
                fallback_count = 1
            groups = [(w, fallback_count) for w in self.attacker.weapons]
            self.status.set('Base loadout could not be mapped exactly; showing fallback weapon counts.')

        self.weapon_groups = groups
        labels = [f'{weapon.name} ×{count} [{weapon.weapon_type}]' for weapon, count in groups]
        self.attacker_weapon['values'] = labels
        if labels:
            self.attacker_weapon.current(0)
            self.update_weapon_stats()
        else:
            self.attacker_weapon.set('No equipped weapons')
            self.update_weapon_stats()

    def selected_weapon_group(self) -> Optional[Tuple[Weapon, int]]:
        idx = self.attacker_weapon.current()
        if idx < 0 or idx >= len(self.weapon_groups):
            return None
        return self.weapon_groups[idx]

    def update_weapon_stats(self):
        self.weapon_stats.delete('1.0', tk.END)
        group = self.selected_weapon_group()
        if not group:
            self.weapon_stats.insert(tk.END, 'No weapon selected')
            return
        weapon, count = group
        self.weapon_stats.insert(
            tk.END,
            f'{weapon.name} ×{count} | {weapon.weapon_type} {weapon.range}\n'
            f'A {dice_to_string(weapon.attacks_dice)} | {"WS" if weapon.is_melee else "BS"} {weapon.bs_ws}+ | '
            f'S {weapon.strength} | AP {weapon.ap} | D {dice_to_string(weapon.damage_dice)}\n'
            f'{weapon.keyword_string()}'
        )

    def current_modifiers(self) -> dict:
        return dict(
            half_range=self.half_range.get(),
            cover=self.cover.get(),
            charging=self.charging.get(),
            moved_more_than_3=self.moved.get(),
            hit_reroll=self.hit_reroll.get(),
            wound_reroll=self.wound_reroll.get(),
            sustained_override=int(self.sustained.get()),
            lethal_override=self.lethal.get(),
        )

    def calculate(self):
        if not self.attacker or not self.defender or not self.defender_stats:
            messagebox.showwarning('Selection', 'Select attacker and defender first.')
            return
        group = self.selected_weapon_group()
        if not group:
            messagebox.showwarning('Weapon', 'No equipped weapon selected.')
            return
        try:
            defender_count = int(self.defender_count.get())
        except ValueError:
            defender_count = 10
        weapon, count = group
        result = calculate_attack(
            weapon, count, self.defender_stats, defender_count,
            self.defender.keywords, **self.current_modifiers()
        )
        self.last_result = result
        self.display_result(result, weapon)

    def display_result(self, result: AttackResult, weapon: Weapon):
        self.result_text.delete('1.0', tk.END)
        out = [
            '=' * 88,
            f'{result.weapon_count} equipped copy/copies of {result.weapon_name}',
            f'vs {result.defender_count} × {result.defender_model}',
            '=' * 88,
            '',
            f'Weapon: A {dice_to_string(weapon.attacks_dice)}  {"WS" if weapon.is_melee else "BS"} {weapon.bs_ws}+  '
            f'S {weapon.strength}  AP {weapon.ap}  D {dice_to_string(weapon.damage_dice)}',
            f'Keywords: {weapon.keyword_string()}',
            '',
            'Per-die probabilities:',
            f'  Hit:                    {result.hit_probability * 100:7.2f}%',
            f'  Critical Hit:           {result.critical_hit_probability * 100:7.2f}%',
            f'  Wound (rolled hit):     {result.wound_probability * 100:7.2f}%',
            f'  Critical Wound:         {result.critical_wound_probability * 100:7.2f}%',
            '',
            'Expected values:',
            f'  Attacks:                 {result.avg_attacks:8.3f}',
            f'  Hits (incl. Sustained):  {result.avg_hits:8.3f}',
            f'  Wounds:                  {result.avg_wounds:8.3f}',
            f'  Failed normal saves:     {result.regular_failed_saves:8.3f}',
            f'  Devastating bypasses:    {result.devastating_wounds:8.3f}',
            f'  Raw average damage:      {result.avg_damage:8.3f}',
            '',
            'Exact casualty model:',
            f'  Expected kills:          {result.expected_kills:8.3f}',
            f'  Chance to kill >=1:      {result.kill_probability * 100:7.2f}%',
            f'  Avg wounds on survivor:  {result.expected_remaining_wounds_on_current:8.3f}',
            '',
            'Effective damage distribution (after overkill is discarded):',
        ]
        for damage, prob in sorted(result.effective_damage_distribution.items()):
            if prob >= 0.002:
                bar = '█' * min(50, int(prob * 50))
                out.append(f'  {damage:3d}: {prob * 100:6.2f}% {bar}')
        self.result_text.insert(tk.END, '\n'.join(out))
        self.status.set('Calculation complete - current wargear loadout is included.')

    def compare_weapons(self):
        if not self.defender or not self.defender_stats or not self.weapon_groups:
            messagebox.showwarning('Selection', 'Select attacker, defender and equipped weapons first.')
            return
        try:
            defender_count = int(self.defender_count.get())
        except ValueError:
            defender_count = 10
        rows = []
        for weapon, count in self.weapon_groups:
            result = calculate_attack(
                weapon, count, self.defender_stats, defender_count,
                self.defender.keywords, **self.current_modifiers()
            )
            rows.append((weapon, count, result))
        rows.sort(key=lambda item: (item[2].expected_kills, item[2].avg_damage), reverse=True)

        self.result_text.delete('1.0', tk.END)
        out = [
            '=' * 110,
            f'EQUIPPED WEAPON COMPARISON vs {defender_count} × {self.defender_stats.name}',
            'Wargear selections are reflected in the copy count shown below.',
            '=' * 110,
            f"{'Weapon':<34} {'Qty':>4} {'Attacks':>9} {'Hits':>9} {'Wounds':>9} {'Damage':>9} {'Kills':>9} {'P(kill)':>9}",
            '-' * 110,
        ]
        for weapon, count, result in rows:
            label = f'{weapon.name} [{weapon.weapon_type}]'[:34]
            out.append(
                f'{label:<34} {count:>4} {result.avg_attacks:>9.2f} {result.avg_hits:>9.2f} '
                f'{result.avg_wounds:>9.2f} {result.avg_damage:>9.2f} {result.expected_kills:>9.2f} '
                f'{result.kill_probability * 100:>8.1f}%'
            )
        self.result_text.insert(tk.END, '\n'.join(out))
        self.status.set('Compared currently equipped weapon groups.')

    def clear_results(self):
        self.result_text.delete('1.0', tk.END)
        self.last_result = None

    def export_results(self):
        text = self.result_text.get('1.0', tk.END).strip()
        if not text:
            messagebox.showwarning('Export', 'Nothing to export.')
            return
        filename = 'mathhammer_results.txt'
        try:
            with open(filename, 'w', encoding='utf-8') as fh:
                fh.write(text + '\n')
            messagebox.showinfo('Export', f'Saved to {filename}')
        except Exception as exc:
            messagebox.showerror('Export', str(exc))


def main():
    root = tk.Tk()
    MathHammerGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
