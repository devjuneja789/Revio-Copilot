"""Hand-built English + romanised-Hindi (Hinglish) lexicons for the offline rules engine.

This is deliberately small and auditable. It is the *fallback and safety net* of the system:
in production the LLM does the nuanced reading and these rules guarantee that a missed
legal/health/privacy threat can never be silently dropped (flags are the union of both).
"""
from __future__ import annotations

# ----------------------------------------------------------------------------- sentiment words
STRONG = 2.0
NORMAL = 1.0

POS_STRONG = {
    "fantastic", "amazing", "excellent", "awesome", "superb", "outstanding", "best", "love", "loved",
    "wonderful", "perfect", "perfectly", "delighted", "zabardast", "shandar", "lajawab", "behtareen",
    "badhiya", "fabulous",
}
POS = {
    "good", "great", "lovely", "delicious", "tasty", "yummy", "fresh", "crispy", "polite", "friendly",
    "caring", "helpful", "clean", "hygienic", "quick", "quickly", "fast", "faster", "efficient", "nice",
    "pleasant", "convenient", "satisfied", "gentle", "thorough", "reasonable", "welcoming", "courteous",
    "happy", "enjoyed", "improved", "apologetic", "apologise", "apologize", "apologised", "apologized",
    "warm", "decent", "recommend", "recommended", "thanks", "thank", "patiently", "complimentary",
    "mast", "achha", "accha", "acha", "tasty", "ekdum", "friendly", "prompt", "speedy", "cozy",
    "wasool", "perfectly",
}
NEG_STRONG = {
    "terrible", "worst", "awful", "horrible", "pathetic", "disgusting", "cheat", "cheats", "cheated",
    "cheating", "scam", "fraud", "poisoning", "humiliating", "derogatory", "ghatiya", "bakwaas",
    "hospitalised", "hospitalized", "disgusted", "unacceptable",
}
NEG = {
    "bad", "rude", "arrogant", "dirty", "filthy", "cold", "stale", "slow", "late", "delay", "delayed",
    "expensive", "overpriced", "pricey", "poor", "waste", "wasted", "unhygienic", "sticky", "noisy",
    "loud", "crowded", "cramped", "confusing", "crashing", "crashed", "avoid", "disappointed",
    "disappointing", "mediocre", "bland", "tasteless", "spilled", "lost", "ignored", "shouted",
    "laughed", "hassle", "infected", "swollen", "vomiting", "worse", "wrong", "expired", "flies",
    "cockroach", "leaked", "spam", "refused", "violation", "misdiagnosed", "attitude", "overcharged",
    "bekar", "ganda", "thanda", "kharab", "mehnga", "pathetic", "disrespectful", "unprofessional",
    "careless", "uncomfortable", "complaint", "reaction", "fatal", "forever",
}
NEUTRAL_CUES = {"okay", "ok", "average", "so-so", "fine"}

INTENSIFIERS = {"very", "really", "extremely", "absolutely", "totally", "so", "too", "seriously", "bahut", "bohot"}
DIMINISHERS = {"bit", "slightly", "little", "somewhat", "kinda"}
NEGATORS = {"not", "no", "never", "without", "hardly", "cannot", "nothing", "nahi", "nahin", "nhi", "neither"}
POST_NEGATORS = {"nahi", "nahin", "nhi"}  # Hindi negation follows the word: "paisa wasool nahi hai"
HEDGES = {"could", "should", "wish", "wished", "needs", "need"}

# multi-word phrases: tuple of tokens -> weight (longest match wins; phrases already encode negation)
PHRASES: dict[tuple[str, ...], float] = {
    ("would", "not", "recommend"): -2.5,
    ("not", "recommend"): -2.0,
    ("paisa", "wasool", "nahi"): -2.0,
    ("paisa", "wasool"): 1.5,
    ("jawab", "nahi"): 2.0,
    ("waste", "of", "money"): -2.0,
    ("not", "worth"): -1.5,
    ("never", "coming", "back"): -2.0,
    ("do", "not", "go"): -2.0,
    ("took", "forever"): -1.5,
    ("no", "clue"): -1.5,
    ("not", "working"): -1.2,
    ("hair", "in"): -1.5,
    ("too", "high"): -1.2,
    ("too", "loud"): -1.5,
    ("gone", "up"): -0.8,
    ("laughed", "it", "off"): -1.5,
    ("shouted", "at"): -2.0,
    ("without", "telling"): -1.5,
    ("refused", "to"): -1.2,
    ("made", "to", "wait"): -1.5,
    ("had", "to", "wait"): -0.8,
    ("nothing", "to", "complain"): 1.0,
    ("personal", "touch"): 1.5,
    ("worth", "it"): 1.0,
    ("thank", "you"): 1.0,
    ("highly", "recommend"): 2.0,
    ("will", "recommend"): 1.5,
    ("will", "come", "again"): 1.5,
    ("will", "visit", "again"): 1.5,
    ("took", "great", "care"): 2.0,
    ("made", "it", "easy"): 1.0,
    ("hands", "down"): 1.0,
    ("did", "not", "bother"): -1.0,
    ("wrong", "medicine"): -2.0,
    ("nothing", "special"): 0.0,
    ("nothing", "terrible"): 0.0,
    ("not", "too", "heavy"): 0.5,
}
NEUTRAL_PHRASES = {("nothing", "special"), ("nothing", "terrible")}
# overall verdicts: when present they settle a pos/neg tie ("fantastic way to wait 2 hours... would not recommend")
VERDICT_NEG = {("would", "not", "recommend"), ("not", "recommend"), ("do", "not", "go"), ("never", "coming", "back"), ("waste", "of", "money")}
VERDICT_POS = {("highly", "recommend"), ("will", "recommend"), ("will", "come", "again"), ("will", "visit", "again"), ("hands", "down")}

# ----------------------------------------------------------------------------- aspects
ASPECT_TOKENS: dict[str, set[str]] = {
    "quality": {
        "food", "taste", "tasty", "delicious", "yummy", "dish", "meal", "portion", "menu", "dal", "paneer",
        "biryani", "thali", "pasta", "chicken", "kachori", "dessert", "lassi", "churma", "baati", "maas",
        "tikka", "lababdar", "khana", "treatment", "doctor", "dr", "consultation", "physiotherapy",
        "ilaaj", "medicine", "catering", "chutney", "kebab", "cooking", "flavour", "flavor",
    },
    "staff": {
        "staff", "waiter", "waitress", "manager", "team", "server", "receptionist", "reception", "nurse",
        "owner", "host", "behaviour", "behavior", "attitude", "rude", "polite", "friendly", "caring",
        "welcoming", "courteous", "helpful", "apologetic", "apologise", "apologize", "gentle", "arrogant",
        "shouted", "ignored", "patiently", "unprofessional", "disrespectful",
    },
    "wait_time": {
        "wait", "waited", "waiting", "slow", "quick", "quickly", "fast", "faster", "delay", "delayed",
        "queue", "prompt", "speedy", "minutes", "mins", "hours", "forever",
    },
    "cleanliness": {
        "clean", "cleaner", "dirty", "hygiene", "hygienic", "unhygienic", "washroom", "washrooms", "toilet",
        "toilets", "flies", "cockroach", "sticky", "filthy", "smell", "smelly",
    },
    "price": {
        "price", "prices", "pricey", "expensive", "overpriced", "cost", "costly", "fee", "fees", "cheap",
        "reasonable", "value", "wasool", "mehnga", "money",
    },
    "ambience": {
        "ambience", "ambiance", "music", "decor", "ac", "atmosphere", "crowded", "noisy", "noise", "loud",
        "cramped", "seating", "lighting", "vibe",
    },
    "billing": {
        "bill", "billing", "charged", "charge", "charges", "refund", "payment", "upi", "invoice", "receipt",
        "overcharged",
    },
    "access": {
        "parking", "valet", "location", "booking", "website", "reservation", "reserved", "booked", "app",
    },
    "safety": {
        "poisoning", "allergic", "allergy", "vomiting", "hospital", "hospitalised", "hospitalized", "er",
        "infected", "swollen", "reaction", "fatal", "ambulance",
    },
}
# multi-token aspect keywords
ASPECT_PHRASES: dict[tuple[str, ...], str] = {
    ("hair", "in"): "cleanliness",
    ("stomach", "pain"): "safety",
    ("service", "charge"): "billing",
    ("waiting", "area"): "ambience",
    ("booking", "system"): "access",
}
SPEED_TOKENS = {"quick", "quickly", "fast", "faster", "slow", "slower", "prompt", "late", "delay", "delayed", "wait", "waited", "waiting"}

# ----------------------------------------------------------------------------- risk flags (regex on lowercase text)
FLAG_PATTERNS: dict[str, list[str]] = {
    "health_safety": [
        r"food poisoning", r"\bpoisoned\b", r"hospitali[sz]ed", r"\bvomit\w*", r"stomach (?:pain|ache|infection)",
        r"\ballerg(?:ic|y|ies)\b", r"allergic reaction", r"\banaphyla\w*", r"rush(?:ed)? to (?:a |the )?(?:doctor|hospital|er)\b",
        r"visit(?:ed)? (?:the )?(?:er|emergency|hospital)\b", r"\bambulance\b", r"\binfected\b", r"\bswollen\b",
        r"\bfatal\b", r"\bexpired\b", r"misdiagnos\w*", r"wrong medicine", r"wrong medication", r"had to admit",
        r"got (?:very |severely )?sick", r"fell sick",
    ],
    "legal_threat": [
        r"\blawyer\b", r"\badvocate\b", r"\battorney\b", r"legal action", r"take legal", r"\bsue\b", r"\bsuing\b",
        r"consumer (?:court|forum|commission|complaint)", r"\bcourt\b", r"\bpolice\b", r"\bfir\b", r"\bfssai\b",
        r"food safety (?:department|officer|authority|inspector)", r"legal notice", r"report(?:ing)? (?:this )?to (?:the )?(?:fssai|police|authorit\w+|health department)",
        r"complaint (?:with|to|against) (?:the )?(?:food|health|police|consumer)",
    ],
    "discrimination_harassment": [
        r"\bracist\b", r"\bracism\b", r"\bcasteist\b", r"\bcaste\b", r"\bsexist\b", r"discriminat\w+", r"\bderogatory\b",
        r"harass\w*", r"molest\w*", r"\bgroped\b", r"because of my (?:religion|caste|gender|race|skin|color|colour)",
        r"because (?:we|i) (?:are|am|were|was) from", r"treated (?:badly|differently) because",
        r"abusive language",
    ],
    "fraud_billing": [
        r"\bscam\w*", r"\bcheat\w*", r"\bfraud\w*", r"overcharg\w*", r"charged (?:me )?twice", r"double[- ]charged",
        r"hidden (?:charge|fee)s?", r"without (?:telling|informing|asking)", r"refused (?:to )?refund",
        r"advertised (?:as|at)", r"\bripped? off\b", r"\bloot\w*",
    ],
    "privacy": [
        r"(?:leaked|shared|sold|exposed) my (?:phone|number|data|report|reports|details|email|information|records?)",
        r"shared my \w+(?: \w+)? (?:report|reports|records?)", r"spam calls?", r"without (?:my )?consent",
        r"privacy", r"data breach", r"personal (?:data|details|information)",
    ],
    "viral_press": [
        r"(?:will|going to|gonna|i'?ll|make sure|let)\b.{0,60}\b(?:post|tell|share|expose|go to|inform|know|tag)\b.{0,60}\b(?:instagram|twitter|facebook|youtube|media|news|press|everyone|everybody|viral|reddit|social media)",
        r"\bgo(?:ing)? viral\b", r"\bjournalist\b", r"news channels?",
    ],
}

TIER_BY_FLAG = {
    "health_safety": "critical",
    "legal_threat": "critical",
    "discrimination_harassment": "high",
    "fraud_billing": "high",
    "privacy": "high",
    "viral_press": "high",
}

HINGLISH_MARKERS = {
    "hai", "hain", "nahi", "nahin", "aur", "bahut", "bhi", "ekdum", "khana", "mast", "yaar", "tha", "thi",
    "achha", "accha", "badhiya", "bekar", "paisa", "wasool", "sab", "samjhaya", "ilaaj", "sahab", "jagah",
    "ghatiya", "thanda", "mehnga", "dikhaya", "jawab", "aap", "hum", "kya", "lekin", "magar", "ne", "ka", "ki", "ko",
    "bhai", "dost", "shukriya", "dhanyavaad", "bohot", "kaafi", "wala", "wali",
}
