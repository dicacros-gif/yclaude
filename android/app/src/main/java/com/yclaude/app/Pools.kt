package com.yclaude.app

/**
 * Word and phrase pools for metadata generation.
 *
 * Everything here is deliberately clean text only (letters and spaces, no
 * punctuation, no emoji). Generation draws from these pools with a fresh random
 * each time so that "Regenerate" yields genuinely different output. Pools are
 * intentionally large to keep titles, descriptions and tags from repeating.
 *
 * Safety: nothing here references banned topics, the standalone token "ai", or
 * the word "lyrics" (long form forbids that label word).
 */
object Pools {

    /** Situational scene phrases for title hooks (the "street dance battle" type). */
    val scenarios: List<String> = listOf(
        "stepping into a midnight street dance battle",
        "chasing neon lights down an endless highway",
        "lost inside a rooftop summer rave",
        "racing the sunrise after a sleepless night",
        "dancing through a downtown thunderstorm",
        "drifting across a moonlit coastline",
        "owning the stage under crimson spotlights",
        "running free through a glittering night city",
        "falling in love on the last train home",
        "burning the floor at an underground club",
        "floating above the clouds at golden hour",
        "breaking every rule on a neon dancefloor",
        "walking out like the main character",
        "turning heartbreak into pure firepower",
        "escaping the world on a coastal drive",
        "rising from the ashes one beat at a time",
        "claiming the spotlight no one saw coming",
        "spinning through a rain soaked alley",
        "chasing a dream across a sleepless skyline",
        "lighting up the dark with every step",
        "leaving the past behind at full speed",
        "moving like the night belongs to you",
        "finding magic in a quiet 3am city",
        "dancing in the headlights of an empty road",
        "stealing the show at a secret rooftop party",
        "writing a comeback story in real time",
        "chasing summer across a glowing horizon",
        "feeling unstoppable under a desert moon",
        "turning an ordinary night into a legend",
        "diving headfirst into a wave of sound",
        "carving a path through the city lights",
        "soaring over a skyline that never sleeps",
        "letting the bass carry every worry away",
        "stepping into a world that finally feels alive",
        "blazing through the dark like a shooting star"
    )

    /** Emotional adjectives that read as high quality mood signals. */
    val moods: List<String> = listOf(
        "nostalgic", "triumphant", "melancholic", "euphoric", "bittersweet",
        "hypnotic", "cinematic", "dreamy", "fierce", "serene",
        "electric", "haunting", "radiant", "restless", "untamed",
        "tender", "defiant", "weightless", "yearning", "fearless",
        "glowing", "wistful", "rebellious", "soothing"
    )

    /** Micro genres and trend genres. */
    val genres: List<String> = listOf(
        "brazilian phonk", "deep house 2026", "hard techno lounge", "future bass",
        "lofi beats", "synthwave", "melodic dubstep", "amapiano", "jersey club",
        "hyperpop", "city pop", "drift phonk", "afro house", "uk garage",
        "trance revival", "indie pop", "future garage", "dark r and b",
        "dream pop", "house anthem", "chillstep", "neo soul", "ambient wave",
        "electro swing", "tech house", "slowed reverb", "pop punk revival"
    )

    /** Listening contexts and activities (function keywords). */
    val functions: List<String> = listOf(
        "late night drive", "deep focus", "intense workout", "study session",
        "sleep", "coding sprint", "reading", "aura farming", "gym energy",
        "main character moment", "morning run", "rainy day reset",
        "creative flow", "long commute", "weekend cleaning", "sunset cooldown",
        "midnight study", "power nap", "road trip", "solo dinner"
    )

    /** Single token activity words used inside prose. */
    val activities: List<String> = listOf(
        "study", "sleep", "workout", "drive", "coding", "reading",
        "focus", "running", "gaming", "relaxing"
    )

    /** Trend and discovery hashtag words (no hash, no spaces). */
    val trendTags: List<String> = listOf(
        "fyp", "viral", "trending", "shorts", "dancecover", "kpop",
        "phonk", "edit", "gym", "drift", "speedup", "nightcore",
        "aesthetic", "vibes", "maincharacter", "playlist", "newmusic",
        "moodboard", "latenight", "focusflow", "summer2026", "darkacademia",
        "gymtok", "musictok", "coverdance", "dancechallenge", "reels",
        "groove", "afterhours", "soundtrack"
    )

    /** Supporting metadata tag tokens (single words, no spaces). */
    val auxTags: List<String> = listOf(
        "piano", "guitar", "ambient", "retro", "rainsounds", "bassboosted",
        "instrumental", "remix", "acoustic", "vocals", "808", "deepwork",
        "chillout", "background", "study", "calm", "energy", "night",
        "summer", "neon", "dreamy", "groovy"
    )

    /** Emotional opening lines for descriptions (snippet bait, never starts with "this"). */
    val hookLines: List<String> = listOf(
        "Let the rhythm pull you into a world that never slows down",
        "Feel every beat melt the noise of the whole day away",
        "Turn up the volume and let the night carry you forward",
        "Every drop hits like a memory you never want to lose",
        "Press play and watch an ordinary moment become unforgettable",
        "Some songs feel like a movie and this is one of them",
        "Close your eyes and the room turns into a glowing dancefloor",
        "When the bass kicks in nothing else in the world matters",
        "Hold on tight because this groove refuses to let you sit still",
        "One listen and the melody lives in your head rent free",
        "Built for the moments when you finally feel unstoppable",
        "Let the chorus wrap around you like warm summer air",
        "The kind of sound that turns a quiet night into a story",
        "Crank it loud and feel the whole city start to move",
        "A wave of sound made for chasing your boldest mood",
        "Drift into a feeling that words can barely describe"
    )

    /** Creator friendly closing snippets (no ad pitch, no medical claims). */
    val closingLines: List<String> = listOf(
        "Save it to your playlist and share the mood with someone tonight",
        "Drop a comment with how this track made you feel",
        "Follow along for fresh sounds dropping every single week",
        "Add this to your rotation and let the vibe ride with you",
        "Thanks for listening and stay tuned for more on the way",
        "Hit the bell so the next drop finds you first",
        "Loop it freely while you move through your day",
        "More moods like this are always just one play away"
    )

    /** Season and time flavor words for hook line two. */
    val seasons: List<String> = listOf(
        "summer 2026", "late summer", "early autumn", "deep winter",
        "spring bloom", "golden hour", "midnight", "blue hour",
        "festival season", "new year", "rainy season", "endless summer"
    )

    /** Long form section markers in musical order (label only). */
    val sectionMarkers: List<String> = listOf(
        "Intro", "Verse 1", "Pre Chorus", "Chorus", "Verse 2",
        "Pre Chorus", "Chorus", "Bridge", "Climax", "Drop Instrumental", "Outro"
    )

    /** Relative positions (0..1 of total duration) matched to the markers above. */
    val sectionFractions: List<Double> = listOf(
        0.00, 0.06, 0.13, 0.25, 0.40,
        0.55, 0.62, 0.72, 0.82, 0.90, 0.96
    )
}
