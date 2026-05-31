package com.yclaude.app

import java.util.Locale
import kotlin.random.Random

/** User supplied generation inputs. */
data class MetaInput(
    val keywords: String,
    val songTitle: String,
    val lyrics: String,
    val hours: Int,
    val minutes: Int,
    val isShorts: Boolean
)

/** Three independent output blocks. */
data class MetaResult(
    val title: String,
    val description: String,
    val tags: String
)

/**
 * Local, rule based metadata generator (no network, no external service).
 * Draws from [Pools] with a fresh random each call so Regenerate differs.
 *
 * Output rules enforced here:
 *  - Title and description prose are clean text (letters digits spaces only).
 *  - The standalone token "ai" is never emitted; long form also drops "lyrics".
 *  - Description never opens with the word this.
 *  - The playlist URL is always the final line of the description, intact.
 *  - Long form descriptions carry colon formatted chapter timestamps scaled
 *    to the user supplied hours and minutes.
 */
object MetaGen {

    const val PLAYLIST_URL =
        "https://youtube.com/playlist?list=PLjKTu-YcMThdMZ0LggSVPPUTVpFj7GziF&si=mIQiA2rwPQRDD7-B"

    private val flavorWords = listOf("anthem", "wave", "mix", "ride", "escape", "journey", "groove")

    fun generate(input: MetaInput): MetaResult {
        val rnd = Random(System.nanoTime())
        return if (input.isShorts) shorts(input, rnd) else longForm(input, rnd)
    }

    // ---------------------------------------------------------------
    //  Shorts
    // ---------------------------------------------------------------
    private fun shorts(input: MetaInput, rnd: Random): MetaResult {
        val title = buildString {
            append(clampWords(frontPhrase(input, rnd) + " " + titleHook(rnd), 42))
            append(' ')
            append(Pools.trendTags.shuffled(rnd).take(4).joinToString(" ") { "#" + it })
        }.let { collapseSpaces(it) }

        val mood = Pools.moods.pick(rnd)
        val genre = Pools.genres.pick(rnd)
        val func = Pools.functions.pick(rnd)

        val desc = buildString {
            appendLine(Pools.hookLines.pick(rnd))
            appendLine(hookTwo(mood, genre, func, rnd))
            appendLine()
            appendLine(
                clean(
                    "Perfect for ${threeActivities(rnd)} and ${func} when you want ${mood} ${genre} energy in seconds ${userSeed(input, rnd)}"
                )
            )
            val lyr = cleanLyrics(input.lyrics, forbidLyrics = false)
            if (lyr.isNotBlank()) {
                appendLine()
                appendLine(lyr)
            }
            appendLine()
            appendLine(clean(Pools.closingLines.pick(rnd) + " moods move from ${mood} to ${Pools.moods.pick(rnd)}"))
            appendLine()
            append(PLAYLIST_URL)
        }

        return MetaResult(title, desc, tagLine(input, rnd))
    }

    // ---------------------------------------------------------------
    //  Long form
    // ---------------------------------------------------------------
    private fun longForm(input: MetaInput, rnd: Random): MetaResult {
        val title = collapseSpaces(
            clampWords(frontPhrase(input, rnd) + " " + titleHook(rnd), 60)
        )

        val mood = Pools.moods.pick(rnd)
        val mood2 = Pools.moods.pick(rnd)
        val genre = Pools.genres.pick(rnd)
        val genre2 = Pools.genres.pick(rnd)
        val func = Pools.functions.pick(rnd)
        val func2 = Pools.functions.pick(rnd)

        val desc = buildString {
            appendLine(Pools.hookLines.pick(rnd))
            appendLine(hookTwo(mood, genre, func, rnd))
            appendLine()
            appendLine(
                clean(
                    "Made for ${threeActivities(rnd)} and ${oneActivity(rnd)} these sounds keep your ${func} flowing from the first beat to the final fade ${userSeed(input, rnd)}"
                )
            )
            appendLine(
                clean(
                    "Blending ${genre} and ${genre2} with ${mood} ${mood2} energy for ${func2} fans of ${Pools.trendTags.shuffled(rnd).take(3).joinToString(" ")} moments"
                )
            )
            appendLine()
            append(buildTimestamps(input.hours, input.minutes))
            appendLine()
            val lyr = cleanLyrics(input.lyrics, forbidLyrics = true)
            if (lyr.isNotBlank()) {
                appendLine()
                appendLine(lyr)
                appendLine()
            }
            appendLine(
                clean(
                    Pools.closingLines.pick(rnd) +
                        " genres span ${genre} ${genre2} moods move from ${mood} to ${mood2} great for ${oneActivity(rnd)} ${oneActivity(rnd)} and ${func}"
                )
            )
            appendLine()
            appendLine(descHashtags(input, rnd))
            append(PLAYLIST_URL)
        }

        return MetaResult(title, desc, tagLine(input, rnd))
    }

    // ---------------------------------------------------------------
    //  Title helpers
    // ---------------------------------------------------------------

    /** Song level phrase placed at the very front of the title. */
    private fun frontPhrase(input: MetaInput, rnd: Random): String {
        val song = cleanInline(input.songTitle)
        if (song.isNotBlank()) {
            val words = bannedFiltered(song, forbidLyrics = false)
            val front = words.take(6).joinToString(" ")
            return if (front.length <= 16) front.uppercase(Locale.US) else front
        }
        val fromLyric = lyricSnippet(input.lyrics, rnd)
        if (fromLyric.isNotBlank()) return fromLyric
        val kw = bannedFiltered(cleanInline(input.keywords), forbidLyrics = false)
        if (kw.isNotEmpty()) return kw.take(5).joinToString(" ")
        return (Pools.genres.pick(rnd) + " " + flavorWords.pick(rnd))
    }

    /** A short catchy line from the lyrics for the title front. */
    private fun lyricSnippet(lyrics: String, rnd: Random): String {
        val lines = lyrics.split("\n").map { it.trim() }.filter { it.isNotBlank() }
        if (lines.isEmpty()) return ""
        val line = lines.pick(rnd)
        val words = bannedFiltered(cleanInline(line), forbidLyrics = false)
        return clampWords(words.joinToString(" "), 24)
    }

    /** A hook fragment after the front phrase: either a scene or a mood genre pair. */
    private fun titleHook(rnd: Random): String =
        if (rnd.nextBoolean()) Pools.scenarios.pick(rnd)
        else "${Pools.moods.pick(rnd)} ${Pools.genres.pick(rnd)} ${flavorWords.pick(rnd)}"

    // ---------------------------------------------------------------
    //  Description helpers
    // ---------------------------------------------------------------

    private fun hookTwo(mood: String, genre: String, func: String, rnd: Random): String =
        clean("A ${mood} ${genre} ${flavorWords.pick(rnd)} built for ${func} and ${Pools.seasons.pick(rnd)}")

    private fun threeActivities(rnd: Random): String =
        Pools.activities.shuffled(rnd).take(3).joinToString(" ")

    private fun oneActivity(rnd: Random): String = Pools.activities.pick(rnd)

    /** Weaves a couple of user keywords into prose, cleaned and safe. */
    private fun userSeed(input: MetaInput, rnd: Random): String {
        val kw = bannedFiltered(cleanInline(input.keywords), forbidLyrics = false)
        if (kw.isEmpty()) return ""
        return "inspired by " + kw.take(5).joinToString(" ")
    }

    // ---------------------------------------------------------------
    //  Timestamps (colon format, scaled to total duration)
    // ---------------------------------------------------------------
    private fun buildTimestamps(hours: Int, minutes: Int): String {
        var total = hours * 3600 + minutes * 60
        if (total <= 0) total = 210 // sensible default ~3:30 when not provided
        val withHours = total >= 3600
        val sb = StringBuilder()
        var prev = -1
        for (i in Pools.sectionMarkers.indices) {
            var sec = (Pools.sectionFractions[i] * total).toInt()
            if (sec <= prev) sec = prev + 1
            if (sec >= total && i < Pools.sectionMarkers.size - 1) sec = total - 1
            prev = sec
            sb.append(formatTime(sec, withHours))
            sb.append(' ')
            sb.append(Pools.sectionMarkers[i])
            if (i < Pools.sectionMarkers.size - 1) sb.append('\n')
        }
        return sb.toString()
    }

    private fun formatTime(sec: Int, withHours: Boolean): String {
        val h = sec / 3600
        val m = (sec % 3600) / 60
        val s = sec % 60
        return if (withHours) "%d:%02d:%02d".format(Locale.US, h, m, s)
        else "%02d:%02d".format(Locale.US, m, s)
    }

    // ---------------------------------------------------------------
    //  Tags and hashtags
    // ---------------------------------------------------------------

    /** Comma separated tag block: genre, function, mood, trend, aux. Nine unique tokens. */
    private fun tagLine(input: MetaInput, rnd: Random): String {
        val out = LinkedHashSet<String>()
        bannedFiltered(cleanInline(input.keywords), forbidLyrics = true)
            .firstOrNull()?.let { compact(it).takeIf { c -> c.isNotBlank() }?.let(out::add) }
        Pools.genres.shuffled(rnd).take(2).forEach { out.add(compact(it)) }
        Pools.functions.shuffled(rnd).take(2).forEach { out.add(compact(it)) }
        out.add(compact(Pools.moods.pick(rnd)))
        Pools.trendTags.shuffled(rnd).take(2).forEach { out.add(compact(it)) }
        Pools.auxTags.shuffled(rnd).forEach { if (out.size < 12) out.add(compact(it)) }
        val nine = out.filter { it.isNotBlank() }.take(9)
        return nine.joinToString(",")
    }

    /** Nine hashtags for the description bottom: brand, genre, mood, trend mix. */
    private fun descHashtags(input: MetaInput, rnd: Random): String {
        val out = LinkedHashSet<String>()
        val brand = compact(
            input.songTitle.ifBlank { input.keywords }.ifBlank { Pools.genres.pick(rnd) }
        )
        if (brand.isNotBlank()) out.add(brand)
        Pools.genres.shuffled(rnd).take(2).forEach { out.add(compact(it)) }
        Pools.moods.shuffled(rnd).take(2).forEach { out.add(compact(it)) }
        Pools.trendTags.shuffled(rnd).forEach { if (out.size < 9) out.add(compact(it)) }
        return out.filter { it.isNotBlank() }.take(9).joinToString(" ") { "#" + it }
    }

    // ---------------------------------------------------------------
    //  Text utilities
    // ---------------------------------------------------------------

    /** Keep letters digits spaces (single line); collapse spaces. */
    private fun cleanInline(s: String): String =
        collapseSpaces(s.replace("\n", " ").replace(Regex("[^A-Za-z0-9 ]"), " "))

    /** Clean a single prose line and strip a leading the word this. */
    private fun clean(s: String): String {
        var t = collapseSpaces(s.replace("\n", " ").replace(Regex("[^A-Za-z0-9 ]"), " "))
        t = t.split(" ").filter { it.lowercase(Locale.US) != "ai" }.joinToString(" ")
        if (t.lowercase(Locale.US).startsWith("this ")) t = t.substring(5)
        return t.trim()
    }

    private fun collapseSpaces(s: String): String =
        s.replace(Regex(" +"), " ").trim()

    /** Tokenize and drop banned standalone words. */
    private fun bannedFiltered(s: String, forbidLyrics: Boolean): List<String> =
        s.split(Regex("\\s+")).filter { w ->
            val lw = w.lowercase(Locale.US)
            w.isNotEmpty() && lw != "ai" && (!forbidLyrics || (lw != "lyrics" && lw != "lyric"))
        }

    /** Multi line lyric cleanup: symbols stripped, banned words removed, blanks dropped. */
    private fun cleanLyrics(raw: String, forbidLyrics: Boolean): String {
        if (raw.isBlank()) return ""
        return raw.split("\n").map { line ->
            val cleaned = line.replace(Regex("[^A-Za-z0-9 ]"), " ")
            bannedFiltered(cleaned, forbidLyrics).joinToString(" ")
        }.filter { it.isNotBlank() }.joinToString("\n")
    }

    /** Collapse to a single lowercase token (no spaces, no symbols). */
    private fun compact(s: String): String =
        s.lowercase(Locale.US).replace(Regex("[^a-z0-9]"), "")

    /** Trim a phrase to whole words within a character budget. */
    private fun clampWords(s: String, maxChars: Int): String {
        val words = s.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
        val sb = StringBuilder()
        for (w in words) {
            val add = if (sb.isEmpty()) w else " $w"
            if (sb.length + add.length > maxChars) break
            sb.append(add)
        }
        return if (sb.isEmpty()) (words.firstOrNull()?.take(maxChars) ?: "") else sb.toString()
    }

    private fun <T> List<T>.pick(rnd: Random): T = this[rnd.nextInt(size)]
}
