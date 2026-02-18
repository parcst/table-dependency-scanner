"""Simple English inflection utilities for Rails-style table name handling.

Covers the most common patterns seen in Rails snake_case table names.
Does not aim to be a full inflector -- just enough accuracy for FK derivation.
"""

# Irregular nouns: plural -> singular
IRREGULAR_PLURAL_TO_SINGULAR: dict[str, str] = {
    "people": "person",
    "men": "man",
    "women": "woman",
    "children": "child",
    "teeth": "tooth",
    "feet": "foot",
    "geese": "goose",
    "mice": "mouse",
    "oxen": "ox",
    "data": "datum",
    "criteria": "criterion",
    "media": "medium",
    "alumni": "alumnus",
    "cacti": "cactus",
    "fungi": "fungus",
    "nuclei": "nucleus",
    "radii": "radius",
    "stimuli": "stimulus",
    "syllabi": "syllabus",
    "analyses": "analysis",
    "bases": "basis",
    "crises": "crisis",
    "diagnoses": "diagnosis",
    "hypotheses": "hypothesis",
    "parentheses": "parenthesis",
    "syntheses": "synthesis",
    "theses": "thesis",
}

# Irregular nouns: singular -> plural
IRREGULAR_SINGULAR_TO_PLURAL: dict[str, str] = {v: k for k, v in IRREGULAR_PLURAL_TO_SINGULAR.items()}


def singularize(word: str) -> str:
    """Convert a plural English word (typically a Rails table name) to singular.

    Handles the most common patterns encountered in Rails snake_case table names.
    Words that are already singular are returned unchanged.
    """
    if not word:
        return word

    lower = word.lower()

    # Preserve compound words (snake_case): singularize only the last segment
    if "_" in lower:
        parts = lower.rsplit("_", 1)
        return parts[0] + "_" + singularize(parts[1])

    # Direct lookup for known irregulars
    if lower in IRREGULAR_PLURAL_TO_SINGULAR:
        return IRREGULAR_PLURAL_TO_SINGULAR[lower]

    # -ies -> -y  (companies -> company, categories -> category)
    if lower.endswith("ies") and len(lower) > 4:
        return lower[:-3] + "y"

    # -ves -> -fe  (knives -> knife, wives -> wife)
    if lower.endswith("ves") and len(lower) > 4:
        # Most -ves words come from -fe originals
        return lower[:-3] + "fe"

    # Words ending in sibilants + es: -sses, -xes, -zes, -ches, -shes -> strip -es
    # (addresses -> address, boxes -> box, churches -> church, dishes -> dish)
    if lower.endswith(("sses", "xes", "zes", "ches", "shes")):
        return lower[:-2]  # strip just the trailing 'es' from e.g. 'addresses' -> 'address'

    # -ses -> -s  (buses -> bus, statuses -> status, processes -> process)
    if lower.endswith("ses") and len(lower) > 4:
        return lower[:-2]  # addresses -> addresse handled above; statuses -> status

    # -oes -> -o  (heroes -> hero, potatoes -> potato)
    if lower.endswith("oes") and len(lower) > 4:
        return lower[:-2]

    # Generic trailing -s: strip exactly one s
    if lower.endswith("s") and not lower.endswith("ss"):
        return lower[:-1]

    return lower


def pluralize(word: str) -> str:
    """Convert a singular English word (typically a Rails model name) to plural.

    Handles the most common patterns encountered in Rails snake_case table names.
    """
    if not word:
        return word

    lower = word.lower()

    # Preserve compound words (snake_case): pluralize only the last segment
    if "_" in lower:
        parts = lower.rsplit("_", 1)
        return parts[0] + "_" + pluralize(parts[1])

    # Direct lookup for known irregulars
    if lower in IRREGULAR_SINGULAR_TO_PLURAL:
        return IRREGULAR_SINGULAR_TO_PLURAL[lower]

    # Already ends with a common plural marker – assume already plural
    if lower.endswith("ies"):
        return lower

    # -fe -> -ves  (knife -> knives, wife -> wives)
    if lower.endswith("fe"):
        return lower[:-2] + "ves"

    # -f -> -ves  (wolf -> wolves, leaf -> leaves) -- only for common patterns
    # (too many false positives with e.g. "belief" -> "beliefs", so skipped here)

    # Consonant + y -> -ies  (company -> companies, category -> categories)
    if lower.endswith("y") and len(lower) > 2 and lower[-2] not in "aeiou":
        return lower[:-1] + "ies"

    # Sibilant endings: -s, -x, -z, -ch, -sh -> -es
    if lower.endswith(("s", "x", "z", "ch", "sh")):
        return lower + "es"

    # -o -> -oes for common words (hero -> heroes)
    # Skipped – too many exceptions (radio -> radios)

    return lower + "s"


def class_name_to_table_name(class_name: str) -> str:
    """Convert a CamelCase Rails model class name to a snake_case plural table name.

    Examples:
      User            -> users
      PostCheckin     -> post_checkins
      UserRichNotification -> user_rich_notifications
      Person          -> people
      Company         -> companies
    """
    import re
    # CamelCase -> snake_case
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()
    return pluralize(snake)
