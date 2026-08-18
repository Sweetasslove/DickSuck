import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import pandas as pd
import re
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass, field
import math
import os

# ============================================================
# 1. HELPER FUNCTIONS
# ============================================================

def parse_stat_value(value_str, default: int = 4) -> int:
    """Parse a stat value that might have special characters."""
    if pd.isna(value_str) or value_str == '' or value_str == '-':
        return default
    
    value_str = str(value_str).strip()
    
    if '*' in value_str:
        match = re.search(r'(\d+)', value_str)
        if match:
            return int(match.group(1))
        return default
    
    if value_str.upper() == 'N/A':
        return default
    
    try:
        return int(value_str)
    except ValueError:
        match = re.search(r'(\d+)', value_str)
        if match:
            return int(match.group(1))
        return default


def parse_save_value(value_str, default: int = 4) -> int:
    """Parse a save value like '4+' or '4'."""
    if pd.isna(value_str) or value_str == '' or value_str == '-':
        return default
    
    value_str = str(value_str).strip()
    value_str = value_str.replace('+', '')
    
    if '*' in value_str:
        match = re.search(r'(\d+)', value_str)
        if match:
            return int(match.group(1))
        return default
    
    if value_str.upper() == 'N/A':
        return default
    
    try:
        return int(value_str)
    except ValueError:
        match = re.search(r'(\d+)', value_str)
        if match:
            return int(match.group(1))
        return default


def parse_dice(dice_str: str) -> Tuple[int, int, int]:
    """Parse dice notation like 'D6', '2D3+1' etc."""
    if pd.isna(dice_str) or dice_str == '' or dice_str == '0':
        return (0, 0, 0)
    
    dice_str = str(dice_str).strip().upper()
    if dice_str == 'N/A' or dice_str == '-':
        return (0, 0, 0)
    
    if dice_str == 'D3' or dice_str == 'D6':
        return (1, int(dice_str[1]), 0)
    
    pattern = r'^(\d*)[Dd](\d+)([+-]\d+)?$'
    match = re.match(pattern, dice_str)
    if not match:
        num_match = re.search(r'(\d+)', dice_str)
        if num_match:
            return (1, 1, int(num_match.group(1)))
        return (0, 0, 0)
    
    num = match.group(1)
    sides = int(match.group(2))
    mod = match.group(3)
    return (int(num) if num else 1, sides, int(mod) if mod else 0)


def parse_keywords(desc: str) -> Dict[str, Any]:
    """Parse weapon keywords from description."""
    if pd.isna(desc) or desc == '':
        return {}
    desc = str(desc).lower().strip()
    keywords = {}
    
    value_flags = ['rapid fire', 'sustained hits', 'melta', 'blast']
    for flag in value_flags:
        match = re.search(rf'{re.escape(flag)}\s*\(?\s*(\d+)\s*\)?', desc)
        if match:
            keywords[flag.replace(' ', '_')] = int(match.group(1))
    
    for match in re.finditer(r'anti-(\w+)\s*([\d+]+)', desc):
        anti_type = match.group(1).replace('-', '_')
        anti_value = int(match.group(2).replace('+', ''))
        keywords[f'anti_{anti_type}'] = anti_value
    
    blast_x = re.search(r'blast\s*\(\s*(\d+)\s*\)', desc)
    if blast_x:
        keywords['blast_x'] = int(blast_x.group(1))
        keywords['blast'] = True
    
    cleave_x = re.search(r'cleave\s*\(\s*(\d+)\s*\)', desc)
    if cleave_x:
        keywords['cleave_x'] = int(cleave_x.group(1))
        keywords['cleave'] = True
    
    bool_flags = ['torrent', 'twin-linked', 'heavy', 'assault', 'pistol', 'lance',
                  'devastating wounds', 'lethal hits', 'ignores cover', 'hazardous',
                  'psychic', 'indirect fire', 'one shot', 'extra attacks', 'precision']
    for flag in bool_flags:
        if flag in desc:
            keywords[flag.replace(' ', '_')] = True
    
    if 'close-quarters' in desc:
        keywords['close_quarters'] = True
    
    return keywords


def clean_html(text: str) -> str:
    """Remove HTML tags and clean up text."""
    if pd.isna(text) or text == '':
        return ''
    text = str(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('•', '·').strip()
    return text


def extract_weapon_name(text: str) -> str:
    """Extract weapon name from option text."""
    # Remove common prefixes
    text = re.sub(r'^(his|the|one|any|up to|for every|each|all)\s+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^(model\'s|models\'|model|models)\s+', '', text, flags=re.IGNORECASE)
    
    # Look for weapon patterns
    patterns = [
        r'(\w+\s+\w+\s+\w+)\s+(?:can be replaced|can be equipped|replaced with)',
        r'(\w+\s+\w+)\s+(?:can be replaced|can be equipped|replaced with)',
        r'(\w+)\s+(?:can be replaced|can be equipped|replaced with)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    # If it's a simple "X can be replaced with Y"
    match = re.search(r'^(.*?)\s+can be replaced', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    return text[:30]


# ============================================================
# 2. ENHANCED WARGEAR DATA CLASSES
# ============================================================

@dataclass
class ModelEquipment:
    """Represents a single model's equipment."""
    model_name: str
    weapons: List[str] = field(default_factory=list)
    wargear: List[str] = field(default_factory=list)
    is_character: bool = False
    
    def clone(self) -> 'ModelEquipment':
        return ModelEquipment(
            model_name=self.model_name,
            weapons=self.weapons.copy(),
            wargear=self.wargear.copy(),
            is_character=self.is_character
        )
    
    def get_display_string(self) -> str:
        parts = []
        if self.weapons:
            parts.append(", ".join(self.weapons))
        if self.wargear:
            parts.append(", ".join(self.wargear))
        return ": ".join(parts) if parts else ""


@dataclass
class UnitLoadout:
    """Represents the complete loadout of a unit."""
    unit_name: str
    models: List[ModelEquipment]
    total_points: int = 0
    total_models: int = 0
    
    def clone(self) -> 'UnitLoadout':
        return UnitLoadout(
            unit_name=self.unit_name,
            models=[m.clone() for m in self.models],
            total_points=self.total_points,
            total_models=self.total_models
        )
    
    def get_model_counts(self) -> Dict[str, int]:
        """Get count of each model type."""
        counts = defaultdict(int)
        for model in self.models:
            counts[model.model_name] += 1
        return dict(counts)
    
    def get_display_lines(self) -> List[str]:
        """Get display lines for the loadout."""
        lines = []
        counts = self.get_model_counts()
        
        for model_name, count in counts.items():
            # Get the first model of this type for equipment
            model = next(m for m in self.models if m.model_name == model_name)
            equip_str = model.get_display_string()
            if equip_str:
                lines.append(f"  {count}x {model_name}: {equip_str}")
            else:
                lines.append(f"  {count}x {model_name}")
        
        return lines


@dataclass
class EnhancedWargearOption:
    """Enhanced wargear option with full selection logic."""
    id: int
    description: str
    cleaned_description: str
    button: str
    line: int
    
    # Type classification
    option_type: str  # 'replacement', 'addition', 'toggle', 'per_x_models'
    
    # Target
    target_weapon: Optional[str] = None
    target_model: Optional[str] = None  # e.g., "Aspiring Champion"
    
    # Choices
    choices: List[str] = field(default_factory=list)
    
    # Limits
    max_per_unit: Optional[int] = None  # e.g., 1 for "one model"
    max_per_x_models: Optional[int] = None  # e.g., 5 for "per 5 models"
    unlimited: bool = False  # "any number of models"
    
    # Selection state
    enabled: bool = False
    selected_count: int = 0
    selected_choice: Optional[str] = None
    
    # Model tracking
    applied_to_models: List[int] = field(default_factory=list)  # indices of models
    
    def get_max_allowed(self, unit_size: int) -> int:
        """Get the maximum number of models this option can be applied to."""
        if self.max_per_unit is not None:
            return self.max_per_unit
        if self.max_per_x_models is not None and self.max_per_x_models > 0:
            return unit_size // self.max_per_x_models
        if self.unlimited:
            return unit_size
        return 1
    
    def get_min_required(self) -> int:
        """Get minimum number of models this option requires."""
        if self.max_per_x_models is not None and self.max_per_x_models > 0:
            return self.max_per_x_models
        return 0


# ============================================================
# 3. ENHANCED WARGEAR PARSER
# ============================================================

def parse_enhanced_options(options_df: pd.DataFrame, datasheet_id: str) -> List[EnhancedWargearOption]:
    """Parse wargear options with full rule extraction."""
    if options_df.empty:
        return []
    
    opt_rows = options_df[options_df['datasheet_id'] == datasheet_id]
    if opt_rows.empty:
        return []
    
    parsed_options = []
    option_id = 0
    
    for _, row in opt_rows.iterrows():
        desc = row['description']
        if pd.isna(desc) or desc == '':
            continue
        desc = desc.strip()
        
        if desc == 'None' or desc == '-':
            continue
        
        button = row['button'] if pd.notna(row['button']) else '•'
        line = int(row['line']) if pd.notna(row['line']) else 0
        
        desc_clean = clean_html(desc)
        lower_desc = desc_clean.lower()
        
        # Determine option type
        option_type = 'addition'
        if 'replaced with' in lower_desc or 'replace' in lower_desc:
            option_type = 'replacement'
        elif 'equipped with' in lower_desc:
            option_type = 'addition'
        elif 'can be equipped with' in lower_desc:
            option_type = 'addition'
        
        # Extract target weapon
        target_weapon = None
        if option_type == 'replacement':
            match = re.search(r'(.+?)\s+can be replaced with\s+(.+)', desc_clean, re.IGNORECASE)
            if not match:
                match = re.search(r'(.+?)\s+replaced with\s+(.+)', desc_clean, re.IGNORECASE)
            if match:
                target_weapon = match.group(1).strip()
                choices_text = match.group(2).strip()
            else:
                target_weapon = extract_weapon_name(desc_clean)
                choices_text = desc_clean
        else:
            choices_text = desc_clean
        
        # Extract choices
        choices = []
        # Split by bullet points, commas, or "or"
        choice_parts = re.split(r'[,;•]|\s+or\s+|\s+and\s+', choices_text)
        for part in choice_parts:
            part = part.strip()
            if part and not part.startswith('For') and not part.startswith('Any'):
                # Clean up HTML artifacts
                part = re.sub(r'<[^>]+>', '', part)
                part = part.strip()
                if part and len(part) > 1:
                    choices.append(part)
        
        # If no choices, use the whole description
        if not choices and option_type != 'replacement':
            choices = [desc_clean]
        
        # Determine limits
        max_per_unit = None
        max_per_x_models = None
        unlimited = False
        target_model = None
        
        # Check for "Aspiring Champion" or similar
        if 'aspiring champion' in lower_desc:
            target_model = 'Aspiring Champion'
        
        # Check for "For every X models"
        every_match = re.search(r'for every (\d+) models?', lower_desc)
        if every_match:
            max_per_x_models = int(every_match.group(1))
        
        # Check for "Up to X models"
        up_to_match = re.search(r'up to (\d+)', lower_desc)
        if up_to_match:
            max_per_unit = int(up_to_match.group(1))
        
        # Check for "Any number"
        if 'any number' in lower_desc:
            unlimited = True
        
        # Check for "1 model" or "one model"
        if re.search(r'\b(1|one)\s+model\b', lower_desc):
            if max_per_unit is None:
                max_per_unit = 1
        
        # Check for "For every 5 models" with specific weapons
        if max_per_x_models:
            # This is a per-X-models option with weapon choices
            pass
        
        parsed_options.append(EnhancedWargearOption(
            id=option_id,
            description=desc,
            cleaned_description=desc_clean,
            button=button,
            line=line,
            option_type=option_type,
            target_weapon=target_weapon,
            target_model=target_model,
            choices=choices,
            max_per_unit=max_per_unit,
            max_per_x_models=max_per_x_models,
            unlimited=unlimited
        ))
        option_id += 1
    
    return parsed_options


# ============================================================
# 4. DATA CLASSES (Original)
# ============================================================

@dataclass
class ModelStats:
    name: str
    movement: str
    toughness: int
    save: int
    invuln: Optional[int]
    invuln_description: str
    wounds: int
    leadership: int
    oc: int
    
    @classmethod
    def from_row(cls, row: pd.Series):
        name = row['name'] if pd.notna(row['name']) else ''
        toughness = parse_stat_value(row['T'], default=4)
        save = parse_save_value(row['Sv'], default=4)
        
        invuln_str = str(row['inv_sv']).strip() if pd.notna(row['inv_sv']) else ''
        if invuln_str == '-' or invuln_str == '' or invuln_str == 'N/A':
            invuln = None
        else:
            invuln = parse_save_value(invuln_str, default=6)
            if invuln >= save:
                invuln = None
        
        wounds = parse_stat_value(row['W'], default=1)
        leadership = parse_save_value(row['Ld'], default=7)
        oc = parse_stat_value(row['OC'], default=1)
        
        return cls(
            name=name,
            movement=str(row['M']) if pd.notna(row['M']) else '6"',
            toughness=toughness,
            save=save,
            invuln=invuln,
            invuln_description=str(row['inv_sv_descr']) if pd.notna(row['inv_sv_descr']) else '',
            wounds=wounds,
            leadership=leadership,
            oc=oc
        )


@dataclass
class UnitData:
    id: str
    name: str
    faction_id: str
    faction_name: str
    composition: List[dict]
    models: List[ModelStats]
    keywords: List[str]
    abilities: List[dict]
    options: List[EnhancedWargearOption]
    weapons: List['Weapon']


@dataclass
class Weapon:
    datasheet_id: str
    name: str
    weapon_type: str
    range: str
    attacks_dice: Tuple[int, int, int]
    bs_ws: Optional[int]
    strength: int
    ap: int
    damage_dice: Tuple[int, int, int]
    keywords: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        self.is_torrent = self.keywords.get('torrent', False)
        self.is_blast = self.keywords.get('blast', False)
        self.blast_x = self.keywords.get('blast_x', 0)
        self.is_cleave = self.keywords.get('cleave', False)
        self.cleave_x = self.keywords.get('cleave_x', 0)
        self.is_twin_linked = self.keywords.get('twin_linked', False)
        self.is_heavy = self.keywords.get('heavy', False)
        self.is_assault = self.keywords.get('assault', False)
        self.rapid_fire_value = self.keywords.get('rapid_fire', 0)
        self.melta_value = self.keywords.get('melta', 0)
        self.sustained_value = self.keywords.get('sustained_hits', 0)
        self.is_devastating = self.keywords.get('devastating_wounds', False)
        self.is_lethal = self.keywords.get('lethal_hits', False)
        self.is_lance = self.keywords.get('lance', False)
        self.ignores_cover = self.keywords.get('ignores_cover', False)
        self.is_hazardous = self.keywords.get('hazardous', False)
        self.is_psychic = self.keywords.get('psychic', False)
        self.is_pistol = self.keywords.get('pistol', False)
        self.is_precision = self.keywords.get('precision', False)
        
        self.anti_values = {}
        for key, value in self.keywords.items():
            if key.startswith('anti_'):
                self.anti_values[key.replace('anti_', '')] = value
    
    def get_average_attacks(self, unit_size: int = 0, half_range: bool = False) -> float:
        num_dice, sides, mod = self.attacks_dice
        if num_dice == 0 or sides == 0:
            base = mod
        else:
            base = num_dice * (sides + 1) / 2 + mod
        
        if self.is_blast and self.blast_x > 0 and unit_size > 5:
            base += self.blast_x * (unit_size - 5)
        
        if self.is_cleave and self.cleave_x > 0 and unit_size > 5:
            base += self.cleave_x * (unit_size - 5)
        
        if self.rapid_fire_value > 0 and half_range:
            base += self.rapid_fire_value
        
        return max(0, base)
    
    def get_average_damage(self, half_range: bool = False) -> float:
        num_dice, sides, mod = self.damage_dice
        if num_dice == 0 or sides == 0:
            damage = mod
        else:
            damage = num_dice * (sides + 1) / 2 + mod
        
        if self.melta_value > 0 and half_range:
            damage += self.melta_value
        
        return max(0, damage)
    
    def get_strength(self, target_keywords: List[str] = None) -> int:
        if target_keywords and self.anti_values:
            for keyword in target_keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in self.anti_values:
                    return self.anti_values[keyword_lower]
        return self.strength
    
    def get_keyword_string(self) -> str:
        parts = []
        if self.is_torrent:
            parts.append("Torrent")
        if self.is_blast:
            parts.append(f"Blast({self.blast_x})" if self.blast_x else "Blast")
        if self.is_cleave:
            parts.append(f"Cleave({self.cleave_x})" if self.cleave_x else "Cleave")
        if self.is_twin_linked:
            parts.append("Twin-linked")
        if self.is_heavy:
            parts.append("Heavy")
        if self.is_assault:
            parts.append("Assault")
        if self.rapid_fire_value > 0:
            parts.append(f"Rapid Fire {self.rapid_fire_value}")
        if self.melta_value > 0:
            parts.append(f"Melta {self.melta_value}")
        if self.sustained_value > 0:
            parts.append(f"Sustained Hits {self.sustained_value}")
        if self.is_devastating:
            parts.append("Devastating Wounds")
        if self.is_lethal:
            parts.append("Lethal Hits")
        if self.is_lance:
            parts.append("Lance")
        if self.ignores_cover:
            parts.append("Ignores Cover")
        if self.is_hazardous:
            parts.append("Hazardous")
        if self.is_psychic:
            parts.append("Psychic")
        if self.is_pistol:
            parts.append("Pistol")
        if self.is_precision:
            parts.append("Precision")
        
        for key, value in self.anti_values.items():
            parts.append(f"Anti-{key.capitalize()} {value}+")
        
        return ", ".join(parts) if parts else "None"


# ============================================================
# 5. DATA LOADING (Original with enhanced options)
# ============================================================

FACTION_NAMES = {
    'AC': 'Adeptus Custodes',
    'AdM': 'Adeptus Mechanicus',
    'AE': 'Aeldari',
    'AM': 'Astra Militarum',
    'AoI': 'Agents of the Imperium',
    'AS': 'Adepta Sororitas',
    'CD': 'Chaos Daemons',
    'CSM': 'Chaos Space Marines',
    'DG': 'Death Guard',
    'DRU': 'Drukhari',
    'EC': 'Emperor\'s Children',
    'GC': 'Genestealer Cults',
    'GK': 'Grey Knights',
    'LoV': 'Leagues of Votann',
    'NEC': 'Necrons',
    'ORK': 'Orks',
    'QI': 'Questoris Imperialis',
    'QT': 'Chaos Knights',
    'SM': 'Space Marines',
    'TAU': 'T\'au Empire',
    'TL': 'Titan Legions',
    'TS': 'Thousand Sons',
    'TYR': 'Tyranids',
    'WE': 'World Eaters',
}

UNIT_KEYWORDS = [
    'Infantry', 'Vehicle', 'Monster', 'Walker', 'Flyer', 'Beast', 'Swarm',
    'Cavalry', 'Mounted', 'Dreadnought', 'Terminator', 'Jump Pack',
    'Battlesuit', 'Titanic', 'Character', 'Epic Hero', 'Battleline',
    'Psyker', 'Grenades', 'Smoke', 'Transport', 'Dedicated Transport',
    'Fortification', 'Fly', 'Aircraft', 'Towering', 'Mobile'
]


def load_all_data(base_path: str = '.'):
    """Load all CSV files."""
    files = {
        'units': 'Datasheets.csv',
        'wargear': 'Datasheets_wargear.csv',
        'composition': 'Datasheets_unit_composition.csv',
        'models': 'Datasheets_models.csv',
        'options': 'Datasheets_options.csv',
        'keywords': 'Datasheets_keywords.csv',
        'abilities': 'Datasheets_abilities.csv'
    }
    
    data = {}
    for name, filename in files.items():
        path = os.path.join(base_path, filename)
        if not os.path.exists(path):
            print(f"Warning: {filename} not found at {path}")
            data[name] = pd.DataFrame()
        else:
            try:
                df = pd.read_csv(path, sep='|', dtype=str)
                df.columns = df.columns.str.strip()
                data[name] = df
            except Exception as e:
                print(f"Error loading {filename}: {e}")
                data[name] = pd.DataFrame()
    
    if not data['wargear'].empty:
        data['wargear'] = data['wargear'].dropna(subset=['datasheet_id'])
        data['wargear'] = data['wargear'][data['wargear']['name'].notna() & (data['wargear']['name'] != '')]
        data['wargear'] = data['wargear'][data['wargear']['name'] != 'Example Wargear']
    
    return data


def parse_composition(comp_df: pd.DataFrame, datasheet_id: str) -> List[dict]:
    """Parse unit composition."""
    if comp_df.empty:
        return []
    comp_rows = comp_df[comp_df['datasheet_id'] == datasheet_id]
    if comp_rows.empty:
        return []
    
    models = []
    for _, row in comp_rows.iterrows():
        desc = row['description']
        if pd.isna(desc) or desc == '':
            continue
        desc = desc.strip()
        
        if desc == 'OR' or desc.startswith('OR'):
            continue
        
        desc_clean = re.sub(r'<[^>]+>', '', desc)
        
        range_pattern = r'^(\d+)-(\d+)\s+(.+)$'
        match = re.match(range_pattern, desc_clean)
        if match:
            models.append({
                'name': match.group(3).strip(),
                'min': int(match.group(1)),
                'max': int(match.group(2))
            })
            continue
        
        single_pattern = r'^(\d+)\s+(.+)$'
        match = re.match(single_pattern, desc_clean)
        if match:
            models.append({
                'name': match.group(2).strip(),
                'min': int(match.group(1)),
                'max': int(match.group(1))
            })
            continue
        
        optional_pattern = r'^0-(\d+)\s+(.+)$'
        match = re.match(optional_pattern, desc_clean)
        if match:
            models.append({
                'name': match.group(2).strip(),
                'min': 0,
                'max': int(match.group(1))
            })
            continue
        
        models.append({'name': desc_clean, 'min': 1, 'max': 1})
    
    return models


def get_model_stats(models_df: pd.DataFrame, datasheet_id: str, model_name: str) -> Optional[ModelStats]:
    """Get stats for a model with flexible matching."""
    if models_df.empty:
        return None
    
    model_name_clean = model_name.strip().upper()
    datasheet_models = models_df[models_df['datasheet_id'] == datasheet_id]
    if datasheet_models.empty:
        return None
    
    matching = datasheet_models[datasheet_models['name'].str.upper() == model_name_clean]
    if not matching.empty:
        return ModelStats.from_row(matching.iloc[0])
    
    matching = datasheet_models[datasheet_models['name'].str.upper().str.contains(model_name_clean)]
    if not matching.empty:
        return ModelStats.from_row(matching.iloc[0])
    
    for _, row in datasheet_models.iterrows():
        db_name = str(row['name']).upper()
        if model_name_clean in db_name:
            return ModelStats.from_row(row)
    
    if not datasheet_models.empty:
        return ModelStats.from_row(datasheet_models.iloc[0])
    
    return None


def get_unit_keywords(keywords_df: pd.DataFrame, datasheet_id: str) -> List[str]:
    if keywords_df.empty:
        return []
    kw_rows = keywords_df[keywords_df['datasheet_id'] == datasheet_id]
    if kw_rows.empty:
        return []
    keywords = set()
    for _, row in kw_rows.iterrows():
        keyword = row['keyword']
        if pd.notna(keyword) and keyword != '':
            keywords.add(keyword)
    return sorted(list(keywords))


def get_unit_abilities(abilities_df: pd.DataFrame, datasheet_id: str) -> List[dict]:
    if abilities_df.empty:
        return []
    ab_rows = abilities_df[abilities_df['datasheet_id'] == datasheet_id]
    if ab_rows.empty:
        return []
    abilities = []
    for _, row in ab_rows.iterrows():
        if pd.notna(row['name']) and row['name'] != '':
            abilities.append({
                'name': row['name'],
                'description': row['description'] if pd.notna(row['description']) else '',
                'model': row['model'] if pd.notna(row['model']) else '',
                'type': row['type'] if pd.notna(row['type']) else 'Datasheet'
            })
    return abilities


def parse_weapon(row: pd.Series) -> Weapon:
    """Parse a weapon from a wargear row."""
    bs_ws = None
    if pd.notna(row['BS_WS']) and row['BS_WS'] != 'N/A' and row['BS_WS'] != '-':
        try:
            bs_ws = int(str(row['BS_WS']).replace('+', ''))
        except ValueError:
            bs_ws = None
    
    return Weapon(
        datasheet_id=row['datasheet_id'],
        name=row['name'],
        weapon_type=row['type'] if pd.notna(row['type']) else 'Ranged',
        range=row['range'] if pd.notna(row['range']) else 'Melee',
        attacks_dice=parse_dice(row['A']),
        bs_ws=bs_ws,
        strength=parse_stat_value(row['S'], default=4),
        ap=parse_stat_value(row['AP'], default=0),
        damage_dice=parse_dice(row['D']),
        keywords=parse_keywords(row['description'])
    )


def get_unit_weapons(data: Dict, datasheet_id: str) -> List[Weapon]:
    """Get all weapons for a datasheet."""
    wargear_df = data['wargear']
    wargear_rows = wargear_df[wargear_df['datasheet_id'] == datasheet_id]
    
    weapons = []
    for _, row in wargear_rows.iterrows():
        name = row['name']
        if pd.isna(name) or name == '':
            continue
        try:
            weapon = parse_weapon(row)
            if weapon.attacks_dice[0] > 0 or weapon.attacks_dice[2] > 0:
                weapons.append(weapon)
        except Exception as e:
            continue
    return weapons


def get_unit_data(data: Dict, datasheet_id: str) -> Optional[UnitData]:
    """Get complete unit data for a datasheet."""
    units_df = data['units']
    unit_rows = units_df[units_df['id'] == datasheet_id]
    if unit_rows.empty:
        return None
    
    row = unit_rows.iloc[0]
    name = row['name'] if pd.notna(row['name']) else ''
    faction_id = row['faction_id'] if pd.notna(row['faction_id']) else ''
    faction_name = FACTION_NAMES.get(faction_id, faction_id)
    
    composition = parse_composition(data['composition'], datasheet_id)
    
    models = []
    if composition:
        for comp in composition:
            stats = get_model_stats(data['models'], datasheet_id, comp['name'])
            if stats:
                models.append(stats)
    
    if not models:
        all_models = data['models'][data['models']['datasheet_id'] == datasheet_id]
        if not all_models.empty:
            for _, row2 in all_models.iterrows():
                stats = ModelStats.from_row(row2)
                if stats:
                    models.append(stats)
                    break
    
    if not models:
        stats = get_model_stats(data['models'], datasheet_id, name)
        if stats:
            models.append(stats)
    
    keywords = get_unit_keywords(data['keywords'], datasheet_id)
    abilities = get_unit_abilities(data['abilities'], datasheet_id)
    options = parse_enhanced_options(data['options'], datasheet_id)
    weapons = get_unit_weapons(data, datasheet_id)
    
    return UnitData(
        id=datasheet_id,
        name=name,
        faction_id=faction_id,
        faction_name=faction_name,
        composition=composition,
        models=models,
        keywords=keywords,
        abilities=abilities,
        options=options,
        weapons=weapons
    )


# ============================================================
# 6. PROBABILITY CALCULATIONS (Original)
# ============================================================

def calculate_hit_probability(bs: int, is_torrent: bool = False, is_heavy: bool = False,
                              moved_more_than_3: bool = False, cover: bool = False,
                              is_psychic: bool = False, reroll_ones: bool = False,
                              reroll_all: bool = False, sustained_hits: int = 0) -> Tuple[float, float]:
    if is_torrent:
        return 1.0, 1.0
    
    hit_on = bs
    if is_heavy and moved_more_than_3:
        hit_on += 1
    if cover and not is_psychic:
        hit_on += 1
    if is_psychic:
        hit_on = bs
    
    if hit_on < 2:
        hit_prob = 1.0
    elif hit_on > 6:
        hit_prob = 0.0
    else:
        hit_prob = (7 - hit_on) / 6
    
    fail_prob = 1 - hit_prob
    if reroll_all:
        hit_prob = hit_prob + fail_prob * hit_prob
    elif reroll_ones:
        if hit_on > 2:
            ones_prob = 1/6
            hit_prob = hit_prob + ones_prob * hit_prob
    
    if sustained_hits > 0:
        crit_prob = 1/6
        avg_extra_per_attack = crit_prob * sustained_hits
        return hit_prob, hit_prob + avg_extra_per_attack
    
    return hit_prob, hit_prob


def calculate_wound_probability(strength: int, toughness: int, 
                                anti_values: Dict[str, int] = None,
                                target_keywords: List[str] = None,
                                is_lance: bool = False, charging: bool = False,
                                reroll_ones: bool = False, reroll_all: bool = False,
                                lethal_hits: bool = False) -> float:
    if target_keywords and anti_values:
        for keyword in target_keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in anti_values:
                anti_on = anti_values[keyword_lower]
                if anti_on <= 6:
                    return (7 - anti_on) / 6
    
    if strength >= toughness * 2:
        wound_on = 2
    elif strength > toughness:
        wound_on = 3
    elif strength == toughness:
        wound_on = 4
    elif strength * 2 <= toughness:
        wound_on = 6
    elif strength < toughness:
        wound_on = 5
    else:
        wound_on = 6
    
    if is_lance and charging:
        wound_on = max(2, wound_on - 1)
    
    if wound_on < 2:
        wound_prob = 1.0
    elif wound_on > 6:
        wound_prob = 0.0
    else:
        wound_prob = (7 - wound_on) / 6
    
    fail_prob = 1 - wound_prob
    if reroll_all:
        wound_prob = wound_prob + fail_prob * wound_prob
    elif reroll_ones:
        if wound_on > 2:
            ones_prob = 1/6
            wound_prob = wound_prob + ones_prob * wound_prob
    
    if lethal_hits:
        wound_prob = wound_prob + (1/6) * (1 - wound_prob)
    
    return wound_prob


def calculate_save_probability(save: int, ap: int, invuln: Optional[int] = None,
                               is_devastating: bool = False) -> float:
    if is_devastating:
        return 1.0
    
    if invuln is not None and invuln < save:
        save_needed = invuln
    else:
        save_needed = save
    
    effective_save = save_needed + ap
    if effective_save < 2:
        return 1.0
    if effective_save > 6:
        return 0.0
    return (effective_save - 1) / 6


def get_damage_distribution(weapon: Weapon, half_range: bool = False) -> List[Tuple[int, float]]:
    num_dice, sides, mod = weapon.damage_dice
    
    if num_dice == 0 or sides == 0:
        damage = mod
        if weapon.melta_value > 0 and half_range:
            damage += weapon.melta_value
        return [(max(0, damage), 1.0)]
    
    dist = {0: 1.0}
    for _ in range(num_dice):
        new_dist = {}
        for val, prob in dist.items():
            for i in range(1, sides + 1):
                new_dist[val + i] = new_dist.get(val + i, 0) + prob / sides
        dist = new_dist
    
    result = []
    for val, prob in dist.items():
        damage = val + mod
        if weapon.melta_value > 0 and half_range:
            damage += weapon.melta_value
        damage = max(0, damage)
        result.append((damage, prob))
    
    return result


@dataclass
class AttackResult:
    weapon_name: str
    attacker_count: int
    attacker_model: str
    defender_model: str
    defender_count: int
    
    hit_prob: float
    avg_hits_per_attack: float
    wound_prob: float
    save_fail_prob: float
    
    avg_attacks: float
    avg_hits: float
    avg_wounds: float
    avg_failed_saves: float
    avg_damage_per_failed_save: float
    avg_total_damage: float
    
    expected_kills: float
    expected_wounds_remaining: float
    kill_probability: float
    damage_distribution: Dict[int, float]


def calculate_attack(weapon: Weapon,
                     attacker_stats: ModelStats,
                     attacker_count: int,
                     defender_stats: ModelStats,
                     defender_count: int,
                     defender_keywords: List[str],
                     half_range: bool = False,
                     cover: bool = False,
                     charging: bool = False,
                     moved_more_than_3: bool = False,
                     reroll_hit_ones: bool = False,
                     reroll_hit_all: bool = False,
                     reroll_wound_ones: bool = False,
                     reroll_wound_all: bool = False,
                     sustained_hits: int = 0,
                     lethal_hits: bool = False) -> AttackResult:
    
    bs = weapon.bs_ws if weapon.bs_ws else 4
    
    hit_prob, avg_hits_per_attack = calculate_hit_probability(
        bs=bs,
        is_torrent=weapon.is_torrent,
        is_heavy=weapon.is_heavy,
        moved_more_than_3=moved_more_than_3,
        cover=cover,
        is_psychic=weapon.is_psychic,
        reroll_ones=reroll_hit_ones,
        reroll_all=reroll_hit_all,
        sustained_hits=sustained_hits if not weapon.is_torrent else 0
    )
    
    strength = weapon.get_strength(defender_keywords)
    wound_prob = calculate_wound_probability(
        strength=strength,
        toughness=defender_stats.toughness,
        anti_values=weapon.anti_values,
        target_keywords=defender_keywords,
        is_lance=weapon.is_lance,
        charging=charging,
        reroll_ones=reroll_wound_ones,
        reroll_all=reroll_wound_all,
        lethal_hits=lethal_hits
    )
    
    save_fail_prob = calculate_save_probability(
        save=defender_stats.save,
        ap=weapon.ap,
        invuln=defender_stats.invuln,
        is_devastating=weapon.is_devastating
    )
    
    avg_attacks = weapon.get_average_attacks(defender_count, half_range) * attacker_count
    avg_hits = avg_attacks * avg_hits_per_attack
    avg_wounds = avg_hits * wound_prob
    avg_failed_saves = avg_wounds * save_fail_prob
    
    damage_dist = get_damage_distribution(weapon, half_range)
    avg_damage_per_failed_save = sum(d * p for d, p in damage_dist)
    avg_total_damage = avg_failed_saves * avg_damage_per_failed_save
    
    wounds_per_model = defender_stats.wounds
    expected_kills = avg_total_damage / wounds_per_model
    expected_kills = min(expected_kills, defender_count)
    expected_wounds_remaining = avg_total_damage % wounds_per_model
    
    if avg_total_damage > 0:
        kill_prob = 1 - math.exp(-avg_total_damage / wounds_per_model)
        kill_prob = min(kill_prob, 0.95)
    else:
        kill_prob = 0
    
    damage_distribution = {}
    if avg_total_damage > 0:
        max_dmg = int(avg_total_damage * 2.5) + 5
        for d in range(max_dmg + 1):
            prob = math.exp(-avg_total_damage) * (avg_total_damage ** d) / math.factorial(d)
            if prob > 0.0001:
                damage_distribution[d] = prob
    
    return AttackResult(
        weapon_name=weapon.name,
        attacker_count=attacker_count,
        attacker_model=attacker_stats.name,
        defender_model=defender_stats.name,
        defender_count=defender_count,
        hit_prob=hit_prob,
        avg_hits_per_attack=avg_hits_per_attack,
        wound_prob=wound_prob,
        save_fail_prob=save_fail_prob,
        avg_attacks=avg_attacks,
        avg_hits=avg_hits,
        avg_wounds=avg_wounds,
        avg_failed_saves=avg_failed_saves,
        avg_damage_per_failed_save=avg_damage_per_failed_save,
        avg_total_damage=avg_total_damage,
        expected_kills=expected_kills,
        expected_wounds_remaining=expected_wounds_remaining,
        kill_probability=kill_prob,
        damage_distribution=damage_distribution
    )


# ============================================================
# 7. ENHANCED WARGEAR WIDGET
# ============================================================

class EnhancedWargearWidget:
    """Widget for displaying and selecting wargear with model-by-model control."""
    
    def __init__(self, parent, option: EnhancedWargearOption, 
                 unit_size: int, callback=None):
        self.option = option
        self.unit_size = unit_size
        self.callback = callback
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill=tk.X, pady=2, padx=5)
        
        # Create display text
        display_text = self._get_display_text()
        max_allowed = option.get_max_allowed(unit_size)
        
        # Top row: checkbox + description
        top_frame = ttk.Frame(self.frame)
        top_frame.pack(fill=tk.X)
        
        self.enabled = tk.BooleanVar(value=False)
        self.check = ttk.Checkbutton(
            top_frame, 
            variable=self.enabled,
            command=self._on_toggle
        )
        self.check.pack(side=tk.LEFT)
        
        self.label = ttk.Label(top_frame, text=display_text, 
                               wraplength=400, justify=tk.LEFT)
        self.label.pack(side=tk.LEFT, padx=(5, 10), fill=tk.X, expand=True)
        
        # Second row: controls (count + choice)
        controls_frame = ttk.Frame(self.frame)
        controls_frame.pack(fill=tk.X, padx=(25, 0))
        
        # Count selector
        self.count_spin = None
        if max_allowed > 1:
            ttk.Label(controls_frame, text="Models:").pack(side=tk.LEFT)
            self.count_spin = ttk.Spinbox(
                controls_frame,
                from_=0,
                to=max_allowed,
                width=4,
                state="disabled"
            )
            self.count_spin.set(0)
            self.count_spin.pack(side=tk.LEFT, padx=(5, 10))
            self.count_spin.bind('<KeyRelease>', self._on_count_change)
        
        # Choice dropdown (if multiple choices)
        self.choice_combo = None
        if option.choices and len(option.choices) > 1:
            self.choice_combo = ttk.Combobox(
                controls_frame,
                values=option.choices,
                state="disabled",
                width=25
            )
            if option.choices:
                self.choice_combo.current(0)
                option.selected_choice = option.choices[0]
            self.choice_combo.pack(side=tk.LEFT, padx=5)
            self.choice_combo.bind('<<ComboboxSelected>>', self._on_choice_change)
        
        # Info label showing max
        if max_allowed > 0:
            info_text = f"(max {max_allowed})"
            ttk.Label(controls_frame, text=info_text, font=("", 8, "italic")).pack(side=tk.LEFT, padx=5)
        
        # If there's a target model, show it
        if option.target_model:
            ttk.Label(controls_frame, text=f"[{option.target_model}]", 
                     font=("", 8, "bold")).pack(side=tk.LEFT, padx=5)
    
    def _get_display_text(self) -> str:
        """Get clean display text."""
        text = self.option.cleaned_description
        
        # Truncate if too long
        if len(text) > 100:
            text = text[:97] + "..."
        
        # Add type indicator
        if self.option.option_type == 'replacement':
            if self.option.target_weapon:
                text = f"Replace {self.option.target_weapon} with: {text}"
        elif self.option.option_type == 'addition':
            text = f"Add: {text}"
        
        return text
    
    def _on_toggle(self):
        """Handle checkbox toggle."""
        enabled = self.enabled.get()
        self.option.enabled = enabled
        
        # Enable/disable child widgets
        if self.choice_combo:
            self.choice_combo.config(state="normal" if enabled else "disabled")
        if self.count_spin:
            self.count_spin.config(state="normal" if enabled else "disabled")
            if enabled:
                self.option.selected_count = int(self.count_spin.get())
            else:
                self.option.selected_count = 0
                self.option.applied_to_models = []
        
        if self.callback:
            self.callback()
    
    def _on_count_change(self, *args):
        """Handle count spinbox change."""
        if self.count_spin and self.enabled.get():
            try:
                count = int(self.count_spin.get())
                max_allowed = self.option.get_max_allowed(self.unit_size)
                if count > max_allowed:
                    count = max_allowed
                    self.count_spin.set(count)
                self.option.selected_count = count
                if self.callback:
                    self.callback()
            except ValueError:
                pass
    
    def _on_choice_change(self, *args):
        """Handle choice dropdown change."""
        if self.choice_combo:
            self.option.selected_choice = self.choice_combo.get()
            if self.callback:
                self.callback()
    
    def get_selection(self) -> Optional[Dict]:
        """Get the current selection."""
        if not self.enabled.get():
            return None
        
        return {
            'enabled': True,
            'count': self.option.selected_count,
            'choice': self.option.selected_choice,
            'option': self.option
        }


# ============================================================
# 8. ENHANCED LOADOUT WIDGET
# ============================================================

class LoadoutDisplayWidget:
    """Widget for displaying the unit loadout."""
    
    def __init__(self, parent):
        self.frame = ttk.LabelFrame(parent, text="Unit Loadout", padding="5")
        self.frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        self.text_widget = tk.Text(self.frame, height=8, wrap=tk.WORD, 
                                   font=("Courier", 9), bg="#f0f0f0")
        self.text_widget.pack(fill=tk.BOTH, expand=True)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(self.frame, orient=tk.VERTICAL, 
                                  command=self.text_widget.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_widget.config(yscrollcommand=scrollbar.set)
    
    def update_loadout(self, loadout: UnitLoadout):
        """Update the display with the current loadout."""
        self.text_widget.delete(1.0, tk.END)
        
        if not loadout or not loadout.models:
            self.text_widget.insert(tk.END, "No models loaded")
            return
        
        lines = []
        lines.append(f"📋 {loadout.unit_name} - {loadout.total_models} models")
        if loadout.total_points > 0:
            lines.append(f"   Points: {loadout.total_points}")
        lines.append("")
        
        lines.extend(loadout.get_display_lines())
        
        self.text_widget.insert(tk.END, "\n".join(lines))


# ============================================================
# 9. MAIN GUI APPLICATION (Enhanced)
# ============================================================

class MathHammerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("40k 11th Edition MathHammer")
        self.root.geometry("1900x1000")
        
        self.data = None
        self.units_cache = {}
        
        self.attacker_unit_data = None
        self.defender_unit_data = None
        self.attacker_weapons = []
        self.attacker_stats = None
        self.defender_stats = None
        self.defender_keywords = []
        self.wargear_widgets = []
        self.current_loadout = None
        
        self.all_units = []
        self.filtered_units = {'attacker': [], 'defender': []}
        self.last_result = None
        
        self.create_menu()
        self.create_main_frame()
        self.load_data()
    
    def create_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load Data", command=self.load_data)
        file_menu.add_separator()
        file_menu.add_command(label="Export Results", command=self.export_results)
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.root.config(menu=menubar)
    
    def create_main_frame(self):
        # Main container with paned windows
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left panel: Selection
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)
        
        # Right panel: Results
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=2)
        
        # Selection panel
        selection_frame = ttk.Frame(left_frame)
        selection_frame.pack(fill=tk.BOTH, expand=True)
        
        # Attacker panel
        attacker_panel = ttk.LabelFrame(selection_frame, text="Attacker", padding="10")
        attacker_panel.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 5))
        self.create_unit_selector(attacker_panel, "attacker")
        
        # Defender panel
        defender_panel = ttk.LabelFrame(selection_frame, text="Defender", padding="10")
        defender_panel.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, pady=(5, 0))
        self.create_unit_selector(defender_panel, "defender")
        
        # Right panel: Results and modifiers
        result_top = ttk.Frame(right_frame)
        result_top.pack(fill=tk.BOTH, expand=True)
        
        # Modifiers frame
        mod_frame = ttk.LabelFrame(result_top, text="Modifiers", padding="10")
        mod_frame.pack(side=tk.TOP, fill=tk.X)
        self.create_modifiers(mod_frame)
        
        # Results frame
        result_frame = ttk.LabelFrame(result_top, text="Results", padding="10")
        result_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, pady=(5, 0))
        
        self.result_text = scrolledtext.ScrolledText(result_frame, height=15, font=("Courier", 9))
        self.result_text.pack(fill=tk.BOTH, expand=True)
        
        # Button frame
        btn_frame = ttk.Frame(result_top)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        ttk.Button(btn_frame, text="⚔️ CALCULATE", command=self.calculate, width=15).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📊 Compare Weapons", command=self.compare_all_weapons, width=15).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Clear Results", command=self.clear_results, width=15).pack(side=tk.LEFT, padx=2)
        
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def create_unit_selector(self, parent, side):
        # Faction filter
        faction_frame = ttk.Frame(parent)
        faction_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(faction_frame, text="Faction:").pack(side=tk.LEFT)
        faction_combo = ttk.Combobox(faction_frame, state="readonly", width=20)
        faction_combo.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        faction_combo['values'] = ['All Factions'] + sorted(FACTION_NAMES.values())
        faction_combo.current(0)
        setattr(self, f"{side}_faction_combo", faction_combo)
        faction_combo.bind('<<ComboboxSelected>>', lambda e: self.filter_units(side))
        
        # Keyword filter
        keyword_frame = ttk.Frame(parent)
        keyword_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(keyword_frame, text="Keyword:").pack(side=tk.LEFT)
        keyword_combo = ttk.Combobox(keyword_frame, state="readonly", width=15)
        keyword_combo.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        keyword_combo['values'] = ['All Keywords'] + UNIT_KEYWORDS
        keyword_combo.current(0)
        setattr(self, f"{side}_keyword_combo", keyword_combo)
        keyword_combo.bind('<<ComboboxSelected>>', lambda e: self.filter_units(side))
        
        # Search
        search_frame = ttk.Frame(parent)
        search_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        search_entry = ttk.Entry(search_frame, width=20)
        search_entry.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        setattr(self, f"{side}_search_entry", search_entry)
        search_entry.bind('<KeyRelease>', lambda e: self.filter_units(side))
        
        # Unit list
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        listbox = tk.Listbox(list_frame, height=5, font=("Courier", 9))
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.config(yscrollcommand=scrollbar.set)
        setattr(self, f"{side}_listbox", listbox)
        listbox.bind('<<ListboxSelect>>', lambda e: self.on_unit_select(side))
        
        # Info text
        info_frame = ttk.LabelFrame(parent, text="Unit Info", padding="5")
        info_frame.pack(fill=tk.X, pady=(5, 0))
        info_text = tk.Text(info_frame, height=4, wrap=tk.WORD, font=("Courier", 9))
        info_text.pack(fill=tk.X)
        setattr(self, f"{side}_info_text", info_text)
        
        # Controls
        controls_frame = ttk.Frame(parent)
        controls_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(controls_frame, text="Count:").pack(side=tk.LEFT)
        count_spin = ttk.Spinbox(controls_frame, from_=1, to=40, width=5)
        count_spin.pack(side=tk.LEFT, padx=(5, 0))
        count_spin.set(5 if side == "attacker" else 10)
        setattr(self, f"{side}_count_spin", count_spin)
        count_spin.bind('<KeyRelease>', lambda e: self.on_count_change(side))
        
        ttk.Label(controls_frame, text="Weapon:").pack(side=tk.LEFT, padx=(10, 0))
        weapon_combo = ttk.Combobox(controls_frame, state="readonly", width=20)
        weapon_combo.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        setattr(self, f"{side}_weapon_combo", weapon_combo)
        weapon_combo.bind('<<ComboboxSelected>>', lambda e: self.on_weapon_select(side))
        
        # Weapon stats
        weapon_stats_frame = ttk.LabelFrame(parent, text="Weapon Stats", padding="5")
        weapon_stats_frame.pack(fill=tk.X, pady=(5, 0))
        weapon_stats_text = tk.Text(weapon_stats_frame, height=3, wrap=tk.WORD, font=("Courier", 9))
        weapon_stats_text.pack(fill=tk.X)
        setattr(self, f"{side}_weapon_stats_text", weapon_stats_text)
        
        # Wargear Options - only for attacker
        if side == "attacker":
            wargear_frame = ttk.LabelFrame(parent, text="Wargear Options", padding="5")
            wargear_frame.pack(fill=tk.X, pady=(5, 0))
            
            # Canvas with scrollbar for wargear options
            wargear_canvas = tk.Canvas(wargear_frame, height=150)
            wargear_scrollbar = ttk.Scrollbar(wargear_frame, orient="vertical", 
                                              command=wargear_canvas.yview)
            wargear_scrollable_frame = ttk.Frame(wargear_canvas)
            
            wargear_scrollable_frame.bind(
                "<Configure>",
                lambda e: wargear_canvas.configure(scrollregion=wargear_canvas.bbox("all"))
            )
            
            wargear_canvas.create_window((0, 0), window=wargear_scrollable_frame, anchor="nw")
            wargear_canvas.configure(yscrollcommand=wargear_scrollbar.set)
            
            wargear_canvas.pack(side="left", fill="both", expand=True)
            wargear_scrollbar.pack(side="right", fill="y")
            
            setattr(self, f"{side}_wargear_frame", wargear_scrollable_frame)
            setattr(self, f"{side}_wargear_canvas", wargear_canvas)
            
            # Loadout display
            self.loadout_display = LoadoutDisplayWidget(parent)
    
    def create_modifiers(self, parent):
        # First row - basic modifiers
        row1 = ttk.Frame(parent)
        row1.pack(fill=tk.X)
        
        self.half_range_var = tk.BooleanVar()
        ttk.Checkbutton(row1, text="Half Range", variable=self.half_range_var).pack(side=tk.LEFT, padx=5)
        
        self.cover_var = tk.BooleanVar()
        ttk.Checkbutton(row1, text="Cover (-1 to hit)", variable=self.cover_var).pack(side=tk.LEFT, padx=5)
        
        self.charging_var = tk.BooleanVar()
        ttk.Checkbutton(row1, text="Charging (Lance)", variable=self.charging_var).pack(side=tk.LEFT, padx=5)
        
        self.moved_var = tk.BooleanVar()
        ttk.Checkbutton(row1, text="Moved >3\" (Heavy)", variable=self.moved_var).pack(side=tk.LEFT, padx=5)
        
        # Second row - rerolls
        row2 = ttk.Frame(parent)
        row2.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(row2, text="Hit Rerolls:").pack(side=tk.LEFT, padx=5)
        self.hit_reroll_var = tk.StringVar(value="none")
        rr_frame = ttk.Frame(row2)
        rr_frame.pack(side=tk.LEFT)
        ttk.Radiobutton(rr_frame, text="None", variable=self.hit_reroll_var, value="none").pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(rr_frame, text="1s", variable=self.hit_reroll_var, value="ones").pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(rr_frame, text="All", variable=self.hit_reroll_var, value="all").pack(side=tk.LEFT, padx=2)
        
        ttk.Label(row2, text="Wound Rerolls:").pack(side=tk.LEFT, padx=(20, 5))
        self.wound_reroll_var = tk.StringVar(value="none")
        rr_frame2 = ttk.Frame(row2)
        rr_frame2.pack(side=tk.LEFT)
        ttk.Radiobutton(rr_frame2, text="None", variable=self.wound_reroll_var, value="none").pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(rr_frame2, text="1s", variable=self.wound_reroll_var, value="ones").pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(rr_frame2, text="All", variable=self.wound_reroll_var, value="all").pack(side=tk.LEFT, padx=2)
        
        # Third row - sustained and lethal
        row3 = ttk.Frame(parent)
        row3.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(row3, text="Sustained Hits:").pack(side=tk.LEFT, padx=5)
        self.sustained_var = tk.StringVar(value="0")
        sus_frame = ttk.Frame(row3)
        sus_frame.pack(side=tk.LEFT)
        for v in ['0', '1', '2', '3']:
            ttk.Radiobutton(sus_frame, text=v, variable=self.sustained_var, value=v).pack(side=tk.LEFT, padx=2)
        
        self.lethal_var = tk.BooleanVar()
        ttk.Checkbutton(row3, text="Lethal Hits", variable=self.lethal_var).pack(side=tk.LEFT, padx=(20, 5))
        
        # Defender keywords display
        row4 = ttk.Frame(parent)
        row4.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(row4, text="Defender Keywords:", font=("", 10, "bold")).pack(anchor=tk.W, padx=5)
        self.defender_keywords_text = tk.Text(row4, height=2, wrap=tk.WORD, font=("Courier", 8))
        self.defender_keywords_text.pack(fill=tk.X, padx=5, pady=(2, 0))
    
    def load_data(self):
        self.status_var.set("Loading data...")
        try:
            self.data = load_all_data('.')
            self.all_units = []
            
            for _, row in self.data['units'].iterrows():
                datasheet_id = row['id'] if pd.notna(row['id']) else ''
                if not datasheet_id:
                    continue
                
                try:
                    unit_data = get_unit_data(self.data, datasheet_id)
                    if unit_data:
                        self.units_cache[datasheet_id] = unit_data
                        self.all_units.append({
                            'id': datasheet_id,
                            'name': unit_data.name,
                            'faction_name': unit_data.faction_name,
                            'keywords': unit_data.keywords,
                            'unit_data': unit_data
                        })
                except Exception as e:
                    print(f"Error loading unit {datasheet_id}: {e}")
                    continue
            
            self.status_var.set(f"Loaded {len(self.all_units)} units")
            self.filter_units("attacker")
            self.filter_units("defender")
        except Exception as e:
            self.status_var.set(f"Error loading data: {e}")
            messagebox.showerror("Error", f"Failed to load data: {e}")
    
    def filter_units(self, side):
        faction_combo = getattr(self, f"{side}_faction_combo")
        keyword_combo = getattr(self, f"{side}_keyword_combo")
        search_entry = getattr(self, f"{side}_search_entry")
        listbox = getattr(self, f"{side}_listbox")
        
        faction = faction_combo.get()
        keyword = keyword_combo.get()
        search = search_entry.get().strip().lower()
        
        filtered = []
        for unit in self.all_units:
            if faction != 'All Factions' and unit['faction_name'] != faction:
                continue
            
            if keyword != 'All Keywords':
                unit_keywords = unit.get('keywords', [])
                if keyword not in unit_keywords:
                    continue
            
            if search and search not in unit['name'].lower():
                continue
            
            filtered.append(unit)
        
        listbox.delete(0, tk.END)
        setattr(self, f"{side}_search_results", filtered)
        
        for unit in filtered[:50]:
            listbox.insert(tk.END, f"{unit['name']} ({unit['faction_name']})")
        
        self.status_var.set(f"Found {len(filtered)} units for {side}")
    
    def on_unit_select(self, side):
        listbox = getattr(self, f"{side}_listbox")
        if not listbox.curselection():
            return
        
        idx = listbox.curselection()[0]
        results = getattr(self, f"{side}_search_results")
        if idx >= len(results):
            return
        
        unit_info = results[idx]
        unit_data = unit_info['unit_data']
        
        if side == "attacker":
            self.attacker_unit_data = unit_data
            self.attacker_weapons = unit_data.weapons
            self.attacker_stats = unit_data.models[0] if unit_data.models else None
            self.load_attacker_weapons(unit_data)
            self.load_wargear_options(unit_data)
            self.build_loadout()
        else:
            self.defender_unit_data = unit_data
            self.defender_stats = unit_data.models[0] if unit_data.models else None
            self.defender_keywords = unit_data.keywords
        
        self.update_unit_info(side, unit_data)
    
    def update_unit_info(self, side, unit_data):
        info_text = getattr(self, f"{side}_info_text")
        info_text.delete(1.0, tk.END)
        
        lines = []
        lines.append(f"📋 {unit_data.name}")
        lines.append(f"  Faction: {unit_data.faction_name}")
        
        comp_str = ", ".join([f"{m['min']}-{m['max']} {m['name']}" for m in unit_data.composition])
        lines.append(f"  Composition: {comp_str}")
        
        if unit_data.keywords:
            lines.append(f"  Keywords: {', '.join(unit_data.keywords[:10])}")
        
        if unit_data.models:
            stats = unit_data.models[0]
            invuln_str = f" {stats.invuln}+" if stats.invuln else ""
            lines.append(f"  Stats: M{stats.movement} T{stats.toughness} Sv{stats.save}+{invuln_str} W{stats.wounds} Ld{stats.leadership}+ OC{stats.oc}")
        
        if unit_data.abilities:
            ab_str = ", ".join([a['name'] for a in unit_data.abilities[:3]])
            lines.append(f"  Abilities: {ab_str}")
        
        info_text.insert(tk.END, "\n".join(lines))
        
        if side == "defender" and hasattr(self, 'defender_keywords_text'):
            self.defender_keywords_text.delete(1.0, tk.END)
            self.defender_keywords_text.insert(tk.END, ", ".join(unit_data.keywords))
    
    def load_attacker_weapons(self, unit_data):
        weapons = unit_data.weapons
        self.attacker_weapons = weapons
        
        weapon_combo = self.attacker_weapon_combo
        weapon_combo['values'] = [w.name for w in weapons]
        if weapons:
            weapon_combo.current(0)
            self.update_weapon_stats(self.attacker_weapon_stats_text, weapons[0])
        else:
            weapon_combo.set("No weapons found")
            self.update_weapon_stats(self.attacker_weapon_stats_text, None)
    
    def load_wargear_options(self, unit_data):
        """Load and display enhanced wargear options."""
        wargear_frame = getattr(self, "attacker_wargear_frame")
        
        # Clear existing widgets
        for widget in wargear_frame.winfo_children():
            widget.destroy()
        
        self.wargear_widgets = []
        
        if not unit_data.options:
            ttk.Label(wargear_frame, text="No wargear options available", 
                     font=("", 9, "italic")).pack(pady=5)
            return
        
        # Get unit size
        try:
            unit_size = int(self.attacker_count_spin.get())
        except:
            unit_size = 5
        
        # Display options with enhanced widgets
        for option in unit_data.options:
            # Skip options that don't make sense to show
            if option.cleaned_description.lower().strip() in ['none', 'or', '']:
                continue
            
            widget = EnhancedWargearWidget(
                wargear_frame, 
                option, 
                unit_size,
                callback=self.on_wargear_change
            )
            self.wargear_widgets.append(widget)
        
        # Update canvas height
        wargear_canvas = getattr(self, "attacker_wargear_canvas")
        height = min(250, len(self.wargear_widgets) * 45 + 20)
        wargear_canvas.configure(height=height)
        
        if not self.wargear_widgets:
            ttk.Label(wargear_frame, text="No applicable wargear options", 
                     font=("", 9, "italic")).pack(pady=5)
    
    def on_wargear_change(self):
        """Called when any wargear option changes."""
        self.build_loadout()
    
    def on_count_change(self, side):
        """Called when model count changes."""
        if side == "attacker" and self.attacker_unit_data:
            self.load_wargear_options(self.attacker_unit_data)
            self.build_loadout()
    
    def build_loadout(self):
        """Build the unit loadout from selected wargear."""
        if not self.attacker_unit_data:
            return
        
        unit_data = self.attacker_unit_data
        try:
            unit_size = int(self.attacker_count_spin.get())
        except:
            unit_size = 5
        
        # Create loadout
        loadout = UnitLoadout(
            unit_name=unit_data.name,
            total_models=unit_size
        )
        
        # Build model list from composition
        if unit_data.composition:
            for comp in unit_data.composition:
                # For each model type in composition
                model_name = comp['name']
                min_count = comp.get('min', 1)
                max_count = comp.get('max', 1)
                
                # Determine how many of this model type
                if max_count == 0:
                    continue
                
                count = min(max_count, unit_size)
                if count <= 0:
                    continue
                
                # Add models
                for i in range(count):
                    model = ModelEquipment(
                        model_name=model_name,
                        is_character='champion' in model_name.lower() or 'captain' in model_name.lower()
                    )
                    loadout.models.append(model)
        else:
            # Fallback: use the first model stat
            if unit_data.models:
                model = ModelEquipment(
                    model_name=unit_data.models[0].name,
                    is_character=False
                )
                loadout.models = [model] * unit_size
        
        # Apply wargear selections
        for widget in self.wargear_widgets:
            selection = widget.get_selection()
            if selection:
                option = selection['option']
                count = selection['count']
                choice = selection['choice']
                
                # Apply to models
                for i in range(min(count, len(loadout.models))):
                    model = loadout.models[i]
                    
                    if option.option_type == 'replacement':
                        # Replace target weapon
                        if option.target_weapon and option.target_weapon in model.weapons:
                            model.weapons.remove(option.target_weapon)
                        if choice:
                            model.weapons.append(choice)
                    elif option.option_type == 'addition':
                        if choice and choice not in model.weapons:
                            model.weapons.append(choice)
                    elif option.option_type == 'toggle':
                        if choice and choice not in model.wargear:
                            model.wargear.append(choice)
        
        self.current_loadout = loadout
        self.loadout_display.update_loadout(loadout)
    
    def on_weapon_select(self, side):
        if side == "attacker":
            idx = self.attacker_weapon_combo.current()
            if idx >= 0 and idx < len(self.attacker_weapons):
                self.update_weapon_stats(self.attacker_weapon_stats_text, self.attacker_weapons[idx])
    
    def update_weapon_stats(self, text_widget, weapon):
        text_widget.delete(1.0, tk.END)
        
        if not weapon:
            text_widget.insert(tk.END, "No weapon selected")
            return
        
        lines = []
        attacks_str = f"{weapon.attacks_dice[0]}D{weapon.attacks_dice[1]}" if weapon.attacks_dice[0] > 0 else str(weapon.attacks_dice[2])
        if weapon.attacks_dice[2] > 0 and weapon.attacks_dice[0] > 0:
            attacks_str += f"+{weapon.attacks_dice[2]}"
        
        lines.append(f"  {weapon.name}")
        lines.append(f"  Type: {weapon.weapon_type} | Range: {weapon.range}")
        lines.append(f"  A: {attacks_str} | BS/WS: {weapon.bs_ws}+ | S: {weapon.strength} | AP: {weapon.ap} | D: {weapon.damage_dice}")
        
        kw_str = weapon.get_keyword_string()
        if kw_str and kw_str != "None":
            lines.append(f"  Keywords: {kw_str}")
        
        avg_dmg = weapon.get_average_damage()
        lines.append(f"  Avg Damage: {avg_dmg:.1f}")
        
        text_widget.insert(tk.END, "\n".join(lines))
    
    def get_selected_wargear(self) -> List[Dict]:
        """Get selected wargear options."""
        selected = []
        for widget in self.wargear_widgets:
            selection = widget.get_selection()
            if selection:
                selected.append(selection)
        return selected
    
    def calculate(self):
        if not self.attacker_unit_data:
            messagebox.showwarning("Missing Selection", "Please select an attacker unit.")
            return
        
        if not self.defender_unit_data:
            messagebox.showwarning("Missing Selection", "Please select a defender unit.")
            return
        
        if not self.attacker_weapons:
            messagebox.showwarning("No Weapons", "No weapons found for the attacker.")
            return
        
        weapon_idx = self.attacker_weapon_combo.current()
        if weapon_idx < 0 or weapon_idx >= len(self.attacker_weapons):
            weapon_idx = 0
        weapon = self.attacker_weapons[weapon_idx]
        
        # Get selected wargear
        selected_wargear = self.get_selected_wargear()
        if selected_wargear:
            self.status_var.set(f"Using wargear: {len(selected_wargear)} options selected")
        
        try:
            attacker_count = int(self.attacker_count_spin.get())
        except:
            attacker_count = 5
        
        try:
            defender_count = int(self.defender_count_spin.get())
        except:
            defender_count = 10
        
        half_range = self.half_range_var.get()
        cover = self.cover_var.get()
        charging = self.charging_var.get()
        moved = self.moved_var.get()
        lethal = self.lethal_var.get()
        
        hit_reroll = self.hit_reroll_var.get()
        reroll_hit_ones = hit_reroll == "ones"
        reroll_hit_all = hit_reroll == "all"
        
        wound_reroll = self.wound_reroll_var.get()
        reroll_wound_ones = wound_reroll == "ones"
        reroll_wound_all = wound_reroll == "all"
        
        sustained = int(self.sustained_var.get())
        
        if not self.defender_stats and self.defender_unit_data:
            if self.defender_unit_data.models:
                self.defender_stats = self.defender_unit_data.models[0]
        
        if not self.defender_stats:
            messagebox.showwarning("No Stats", "Could not find defender stats.")
            return
        
        if not self.attacker_stats and self.attacker_unit_data:
            if self.attacker_unit_data.models:
                self.attacker_stats = self.attacker_unit_data.models[0]
        
        if not self.attacker_stats:
            messagebox.showwarning("No Stats", "Could not find attacker stats.")
            return
        
        defender_keywords = self.defender_keywords if self.defender_keywords else ['infantry']
        
        result = calculate_attack(
            weapon=weapon,
            attacker_stats=self.attacker_stats,
            attacker_count=attacker_count,
            defender_stats=self.defender_stats,
            defender_count=defender_count,
            defender_keywords=defender_keywords,
            half_range=half_range,
            cover=cover,
            charging=charging,
            moved_more_than_3=moved,
            reroll_hit_ones=reroll_hit_ones,
            reroll_hit_all=reroll_hit_all,
            reroll_wound_ones=reroll_wound_ones,
            reroll_wound_all=reroll_wound_all,
            sustained_hits=sustained,
            lethal_hits=lethal
        )
        
        self.display_results(result)
        self.last_result = result
    
    def display_results(self, result: AttackResult):
        self.result_text.delete(1.0, tk.END)
        
        output = []
        output.append(f"{'='*80}")
        output.append(f"⚔️  {result.attacker_count} x {result.attacker_model} with {result.weapon_name}")
        output.append(f"   vs {result.defender_count} x {result.defender_model}")
        output.append(f"   (T{self.defender_stats.toughness} Sv{self.defender_stats.save}+ W{self.defender_stats.wounds})")
        output.append(f"{'='*80}\n")
        
        output.append("📊 Per-Attack Probabilities:")
        output.append(f"  Hit:              {result.hit_prob * 100:.1f}%")
        if result.avg_hits_per_attack > result.hit_prob:
            output.append(f"    (with Sustained: {result.avg_hits_per_attack * 100:.1f}% avg hits/attack)")
        output.append(f"  Wound:            {result.wound_prob * 100:.1f}%")
        output.append(f"  Failed Save:      {result.save_fail_prob * 100:.1f}%")
        output.append("")
        
        output.append("📈 Expected Values:")
        output.append(f"  Average Attacks:        {result.avg_attacks:.2f}")
        output.append(f"  Average Hits:           {result.avg_hits:.2f}")
        output.append(f"  Average Wounds:         {result.avg_wounds:.2f}")
        output.append(f"  Average Failed Saves:   {result.avg_failed_saves:.2f}")
        output.append(f"  Avg Damage/Failed Save: {result.avg_damage_per_failed_save:.2f}")
        output.append(f"  Average Total Damage:   {result.avg_total_damage:.2f}")
        output.append("")
        
        output.append("💀 Expected Results:")
        output.append(f"  Expected Kills:         {result.expected_kills:.2f} models")
        output.append(f"  Wounds on last model:   {result.expected_wounds_remaining:.1f}")
        output.append(f"  Approx Kill Chance:     {result.kill_probability * 100:.1f}%")
        output.append("")
        
        output.append("📊 Damage Distribution:")
        sorted_damage = sorted(result.damage_distribution.items(), key=lambda x: x[1], reverse=True)[:12]
        for damage, prob in sorted_damage:
            if prob > 0.005:
                bar = "█" * int(prob * 50)
                output.append(f"  {damage:3d} damage: {prob * 100:5.1f}% {bar}")
        
        # Add selected wargear info
        selected_wargear = self.get_selected_wargear()
        if selected_wargear:
            output.append("\n" + "=" * 80)
            output.append("📦 Selected Wargear Options:")
            for selection in selected_wargear:
                option = selection['option']
                count = selection['count']
                choice = selection['choice']
                desc = option.cleaned_description[:60]
                if len(option.cleaned_description) > 60:
                    desc += "..."
                count_info = f" ({count} models)" if count > 0 else ""
                choice_info = f" -> {choice}" if choice else ""
                output.append(f"  • {desc}{count_info}{choice_info}")
        
        # Add loadout display
        if self.current_loadout:
            output.append("\n" + "=" * 80)
            output.append("📋 Unit Loadout:")
            for line in self.current_loadout.get_display_lines():
                output.append(f"  {line}")
        
        self.result_text.insert(tk.END, "\n".join(output))
    
    def compare_all_weapons(self):
        if not self.attacker_unit_data:
            messagebox.showwarning("Missing Selection", "Please select an attacker unit.")
            return
        
        if not self.defender_unit_data:
            messagebox.showwarning("Missing Selection", "Please select a defender unit.")
            return
        
        if not self.attacker_weapons:
            messagebox.showwarning("No Weapons", "No weapons found for the attacker.")
            return
        
        if not self.defender_stats and self.defender_unit_data:
            if self.defender_unit_data.models:
                self.defender_stats = self.defender_unit_data.models[0]
        
        if not self.defender_stats:
            messagebox.showwarning("No Stats", "Could not find defender stats.")
            return
        
        try:
            attacker_count = int(self.attacker_count_spin.get())
        except:
            attacker_count = 5
        
        try:
            defender_count = int(self.defender_count_spin.get())
        except:
            defender_count = 10
        
        half_range = self.half_range_var.get()
        cover = self.cover_var.get()
        charging = self.charging_var.get()
        moved = self.moved_var.get()
        lethal = self.lethal_var.get()
        
        hit_reroll = self.hit_reroll_var.get()
        reroll_hit_ones = hit_reroll == "ones"
        reroll_hit_all = hit_reroll == "all"
        
        wound_reroll = self.wound_reroll_var.get()
        reroll_wound_ones = wound_reroll == "ones"
        reroll_wound_all = wound_reroll == "all"
        
        sustained = int(self.sustained_var.get())
        defender_keywords = self.defender_keywords if self.defender_keywords else ['infantry']
        
        results = []
        for weapon in self.attacker_weapons:
            result = calculate_attack(
                weapon=weapon,
                attacker_stats=self.attacker_stats,
                attacker_count=attacker_count,
                defender_stats=self.defender_stats,
                defender_count=defender_count,
                defender_keywords=defender_keywords,
                half_range=half_range,
                cover=cover,
                charging=charging,
                moved_more_than_3=moved,
                reroll_hit_ones=reroll_hit_ones,
                reroll_hit_all=reroll_hit_all,
                reroll_wound_ones=reroll_wound_ones,
                reroll_wound_all=reroll_wound_all,
                sustained_hits=sustained,
                lethal_hits=lethal
            )
            results.append((weapon, result))
        
        results.sort(key=lambda x: x[1].expected_kills, reverse=True)
        
        self.result_text.delete(1.0, tk.END)
        output = []
        output.append(f"{'='*80}")
        output.append(f"⚔️  WEAPON COMPARISON")
        output.append(f"   {attacker_count} x {self.attacker_stats.name} vs {defender_count} x {self.defender_stats.name}")
        output.append(f"   (T{self.defender_stats.toughness} Sv{self.defender_stats.save}+ W{self.defender_stats.wounds})")
        output.append(f"{'='*80}\n")
        
        output.append(f"{'Weapon':<30} {'Hits':>8} {'Wounds':>8} {'Failed':>8} {'Damage':>8} {'Kills':>8} {'Kill%':>8}")
        output.append("-" * 80)
        
        for weapon, result in results:
            output.append(f"{weapon.name[:29]:<30} "
                         f"{result.avg_hits:>8.1f} "
                         f"{result.avg_wounds:>8.1f} "
                         f"{result.avg_failed_saves:>8.1f} "
                         f"{result.avg_total_damage:>8.1f} "
                         f"{result.expected_kills:>8.2f} "
                         f"{result.kill_probability * 100:>7.1f}%")
        
        self.result_text.insert(tk.END, "\n".join(output))
    
    def clear_results(self):
        self.result_text.delete(1.0, tk.END)
        self.last_result = None
        self.status_var.set("Results cleared")
    
    def export_results(self):
        if not hasattr(self, 'last_result') or self.last_result is None:
            messagebox.showwarning("No Results", "Please calculate a result first.")
            return
        
        filename = "mathhammer_results.txt"
        try:
            with open(filename, 'w') as f:
                f.write("40k 11th Edition MathHammer Results\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Attacker: {self.last_result.attacker_count} x {self.last_result.attacker_model} with {self.last_result.weapon_name}\n")
                f.write(f"Defender: {self.last_result.defender_count} x {self.last_result.defender_model}\n\n")
                f.write(f"Expected Kills: {self.last_result.expected_kills:.2f}\n")
                f.write(f"Average Damage: {self.last_result.avg_total_damage:.2f}\n")
                f.write(f"Kill Chance: {self.last_result.kill_probability * 100:.1f}%\n")
                
                # Add wargear info
                selected_wargear = self.get_selected_wargear()
                if selected_wargear:
                    f.write("\nSelected Wargear Options:\n")
                    for selection in selected_wargear:
                        option = selection['option']
                        count = selection['count']
                        choice = selection['choice']
                        desc = option.cleaned_description[:60]
                        count_info = f" ({count} models)" if count > 0 else ""
                        choice_info = f" -> {choice}" if choice else ""
                        f.write(f"  - {desc}{count_info}{choice_info}\n")
                
                # Add loadout
                if self.current_loadout:
                    f.write("\nUnit Loadout:\n")
                    for line in self.current_loadout.get_display_lines():
                        f.write(f"  {line}\n")
            
            self.status_var.set(f"Results exported to {filename}")
            messagebox.showinfo("Export Complete", f"Results saved to {filename}")
        except Exception as e:
            self.status_var.set(f"Export error: {e}")
            messagebox.showerror("Export Error", str(e))
    
    def show_about(self):
        messagebox.showinfo("About", 
            "40k 11th Edition MathHammer\n\n"
            "A probability calculator for Warhammer 40k.\n\n"
            "Features:\n"
            "• Full keyword support (Anti, Lethal, Sustained, etc.)\n"
            "• Unit abilities from data files\n"
            "• New Recruit-style wargear selection\n"
            "• Model-by-model loadout display\n"
            "• Weapon comparison mode\n"
            "• Export results to file\n\n"
            "Built with Python and Tkinter.\n"
            "Data from Wahapedia exports.")


# ============================================================
# 10. MAIN
# ============================================================

def main():
    root = tk.Tk()
    app = MathHammerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()