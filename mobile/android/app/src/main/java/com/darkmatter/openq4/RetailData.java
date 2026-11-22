// SPDX-License-Identifier: GPL-3.0-or-later
package com.darkmatter.openq4;

import java.io.File;
import java.io.IOException;
import java.io.InterruptedIOException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

/** Read-only setup preflight. Never repairs retail media or substitutes for engine checks. */
final class RetailData {
    private static final int MAX_FILES = 4096;
    private static final int MAX_ARCHIVES = 128;
    private static final long MAX_EXPANDED_BYTES = 32L * 1024 * 1024 * 1024;

    static final class Expected {
        final String name;
        final int checksum;
        final boolean required;
        Expected(String name, int checksum, boolean required) {
            this.name = name;
            this.checksum = checksum;
            this.required = required;
        }
    }

    /** The retail game directory under the chosen install root (BASE_GAMEDIR). */
    static final String DIRECTORY = "base";

    // Keep this startup baseline in agreement with FileSystem.cpp's
    // officialPk4s. The host test compares every name, value and required flag
    // against that table. A zero checksum is presence-only, as in the engine.
    // No single archive is required: Prey has two complete retail layouts.
    static final List<Expected> OFFICIAL = Collections.unmodifiableList(Arrays.asList(
        new Expected("pak000.pk4", 0x7dc00ede, false),
        new Expected("pak001.pk4", 0xd06647b1, false),
        new Expected("pak002.pk4", 0x57dce443, false),
        new Expected("pak003.pk4", 0x263006fe, false),
        new Expected("pak004.pk4", 0xcc075380, false),
        new Expected("pak_data.pk4", 0xbe295ead, false),
        new Expected("pak_sound.pk4", 0xe0c27ee2, false),
        new Expected("pak_en_v.pk4", 0x952b910e, false),
        new Expected("pak_en_t.pk4", 0x6625f12d, false),
        new Expected("pak005.pk4", 0, false),
        new Expected("pak006.pk4", 0, false),
        new Expected("pak020.pk4", 0, false),
        new Expected("pak040.pk4", 0, false),
        new Expected("game00.pk4", 0, false),
        new Expected("game01.pk4", 0, false),
        new Expected("game02.pk4", 0, false),
        new Expected("game03.pk4", 0, false)
    ));

    // FileSystem.cpp's requiredClassicPk4s and requiredDigitalPk4s: the CD/DVD
    // layout and the consolidated digital one. Either complete set is ready.
    static final List<List<String>> LAYOUTS = Collections.unmodifiableList(Arrays.asList(
        Collections.unmodifiableList(Arrays.asList("pak000.pk4", "pak001.pk4", "pak002.pk4", "pak003.pk4", "pak004.pk4")),
        Collections.unmodifiableList(Arrays.asList("pak_data.pk4", "pak_sound.pk4", "pak_en_v.pk4", "pak_en_t.pk4"))
    ));

    /**
     * The layout the engine validates: a complete one, else the one with the
     * most members present (the classic set on a tie), so diagnostics name the
     * smallest repair. Mirrors idFileSystemLocal's layout detection.
     */
    static List<String> layout(java.util.Collection<String> present) {
        int classic = 0, digital = 0;
        for (String name : LAYOUTS.get(0)) if (present.contains(name)) ++classic;
        for (String name : LAYOUTS.get(1)) if (present.contains(name)) ++digital;
        boolean useDigital = digital == LAYOUTS.get(1).size() ||
            (classic != LAYOUTS.get(0).size() && digital > classic);
        return LAYOUTS.get(useDigital ? 1 : 0);
    }

    static boolean core(String name) {
        String lower = name.toLowerCase(Locale.ROOT);
        for (List<String> set : LAYOUTS) if (set.contains(lower)) return true;
        return false;
    }

    // FileSystem.cpp's fsLanguagePackOrder, kept for parity with the engine.
    // Prey has no zpak_<language> dialogue archives, so a scan never warns
    // about a missing language (the engine's check is Quake 4 only).
    static final List<String> LANGUAGES = Collections.unmodifiableList(Arrays.asList(
        "english", "spanish", "french", "italian", "german", "russian", "polish",
        "korean", "japanese", "chinese", "brazilian", "czech", "hungarian", "turkish", "ukrainian"
    ));

    enum Code {
        DIRECTORY_UNAVAILABLE, LIMIT, DUPLICATE_ARCHIVE, INVALID_ARCHIVE,
        CORRUPT_ENTRY, CHANGED_FILE, UNREADABLE, MISSING_REQUIRED,
        CHECKSUM_MISMATCH, MISSING_OPTIONAL, MISSING_LANGUAGE, UNRECOGNIZED_ARCHIVE
    }

    static final class Issue {
        final Code code;
        final String name;
        final boolean blocking;
        final Integer expectedChecksum, actualChecksum;
        Issue(Code code, String name, boolean blocking) {
            this(code, name, blocking, null, null);
        }
        Issue(Code code, String name, boolean blocking, Integer expected, Integer actual) {
            this.code = code;
            this.name = name;
            this.blocking = blocking;
            expectedChecksum = expected;
            actualChecksum = actual;
        }
    }

    static final class Archive {
        final File file;
        final long bytes, modified, expandedBytes;
        final int checksum;
        Archive(File file, long bytes, long modified, Pk4Checksum.Result result) {
            this.file = file;
            this.bytes = bytes;
            this.modified = modified;
            expandedBytes = result.expandedBytes;
            checksum = result.checksum;
        }
        boolean unchanged() throws IOException {
            return file.equals(file.getCanonicalFile()) && file.isFile() &&
                   file.length() == bytes && file.lastModified() == modified;
        }
    }

    static final class Report {
        final List<Archive> verified;
        final List<Issue> issues;
        Report(List<Archive> verified, List<Issue> issues) {
            this.verified = Collections.unmodifiableList(new ArrayList<>(verified));
            this.issues = Collections.unmodifiableList(new ArrayList<>(issues));
        }
        boolean ready() {
            for (Issue issue : issues) if (issue.blocking) return false;
            return true;
        }
    }

    enum Phase { INSPECTING, VERIFYING }
    interface Progress {
        /** Bytes are uncompressed data; totals are fixed after inspection. False cancels. */
        boolean update(Phase phase, String name, int completed, int archives, long verified, long total);
    }

    private static void progress(Progress observer, Phase phase, String name,
                                 int completed, int count, long verified, long total) throws InterruptedIOException {
        if (Thread.currentThread().isInterrupted() ||
                (observer != null && !observer.update(phase, name, completed, count, verified, total))) {
            throw new InterruptedIOException("Retail validation cancelled");
        }
    }

    static boolean ignoredGameCode(String name) {
        String lower = name.toLowerCase(Locale.ROOT);
        return lower.equals("game000.pk4") || lower.equals("game100.pk4") ||
               lower.equals("game200.pk4") || lower.equals("game300.pk4") ||
               (lower.startsWith("gamex") && lower.endsWith(".pk4"));
    }

    static String baseLanguage(String name) {
        String lower = name.toLowerCase(Locale.ROOT);
        for (String language : LANGUAGES) if (lower.equals("zpak_" + language + ".pk4")) return language;
        return "";
    }

    private static Map<String, File> inventory(File directory, List<Issue> issues) throws IOException {
        Map<String, File> files = new TreeMap<>();
        File[] children = directory.listFiles();
        if (children == null) {
            issues.add(new Issue(Code.DIRECTORY_UNAVAILABLE, directory.getName(), true));
            return files;
        }
        if (children.length > MAX_FILES) {
            issues.add(new Issue(Code.LIMIT, directory.getName(), true));
            return files;
        }
        // Stable diagnostic order independent of filesystem enumeration order.
        Arrays.sort(children);
        for (File child : children) {
            String name = child.getName().toLowerCase(Locale.ROOT);
            if (!name.endsWith(".pk4") || ignoredGameCode(name)) continue;
            if (files.containsKey(name)) {
                issues.add(new Issue(Code.DUPLICATE_ARCHIVE, name, true));
            } else {
                files.put(name, child);
            }
            if (files.size() > MAX_ARCHIVES) {
                issues.add(new Issue(Code.LIMIT, directory.getName(), true));
                return new TreeMap<>();
            }
        }
        return files;
    }

    private static Issue failed(String name, IOException error) {
        Code code = Code.UNREADABLE;
        if (error instanceof Pk4Checksum.Invalid) {
            switch (((Pk4Checksum.Invalid)error).problem) {
                case LIMIT: code = Code.LIMIT; break;
                case INVALID_ARCHIVE: code = Code.INVALID_ARCHIVE; break;
                case CORRUPT_ENTRY: code = Code.CORRUPT_ENTRY; break;
                case CHANGED_FILE: code = Code.CHANGED_FILE; break;
            }
        } else if (error instanceof java.util.zip.ZipException) {
            code = Code.INVALID_ARCHIVE;
        }
        return new Issue(code, name, true);
    }

    static Report scan(File directory, Progress observer) throws IOException {
        return scan(directory, OFFICIAL, observer);
    }

    /** Shared scanner; tests use small independent media with their own known catalogue. */
    static Report scan(File directory, List<Expected> expected, Progress observer) throws IOException {
        progress(observer, Phase.INSPECTING, "", 0, 0, 0, 0);
        File root = directory.getCanonicalFile();
        List<Issue> issues = new ArrayList<>();
        List<Archive> planned = new ArrayList<>(), verified = new ArrayList<>();
        Map<String, File> files = inventory(root, issues);
        boolean invalidInventory = !issues.isEmpty();
        Map<String, Expected> catalogue = new TreeMap<>();
        for (Expected item : expected) catalogue.put(item.name, item);
        // Only the selected retail layout is required; the other layout and
        // the presence-only patch packs vary by edition and are not reported.
        List<String> layout = layout(files.keySet());
        List<String> selected = new ArrayList<>();
        for (String name : layout) if (catalogue.containsKey(name)) selected.add(name);
        for (Expected item : expected) {
            if (!files.containsKey(item.name) && (item.required || selected.contains(item.name))) {
                issues.add(new Issue(Code.MISSING_REQUIRED, item.name, true, item.checksum, null));
            }
        }
        if (invalidInventory) return new Report(verified, issues);
        long total = 0;
        int inspected = 0;
        for (Map.Entry<String, File> item : files.entrySet()) {
            File file = item.getValue();
            final int completed = inspected++;
            try {
                if (!file.equals(file.getCanonicalFile()) || !file.isFile()) {
                    throw new Pk4Checksum.Invalid(Pk4Checksum.Problem.INVALID_ARCHIVE, file.getName());
                }
                long bytes = file.length(), modified = file.lastModified();
                Pk4Checksum.Result result = Pk4Checksum.read(file, false, (done, size) -> {
                    progress(observer, Phase.INSPECTING, file.getName(), completed, files.size(), 0, 0);
                    return true;
                });
                Archive archive = new Archive(file, bytes, modified, result);
                if (!archive.unchanged()) throw new Pk4Checksum.Invalid(Pk4Checksum.Problem.CHANGED_FILE, file.getName());
                if (result.expandedBytes > MAX_EXPANDED_BYTES - total) {
                    issues.add(new Issue(Code.LIMIT, root.getName(), true));
                    return new Report(verified, issues);
                }
                total += result.expandedBytes;
                planned.add(archive);
            } catch (InterruptedIOException cancelled) {
                throw cancelled;
            } catch (IOException error) {
                issues.add(failed(file.getName(), error));
            }
        }
        final long allBytes = total;
        long done = 0;
        int finished = 0;
        for (Archive archive : planned) {
            final long previousBytes = done;
            final int previousCount = finished;
            final long[] readBytes = {0};
            File file = archive.file;
            String name = file.getName().toLowerCase(Locale.ROOT);
            try {
                if (!archive.unchanged()) throw new Pk4Checksum.Invalid(Pk4Checksum.Problem.CHANGED_FILE, name);
                Pk4Checksum.Result full = Pk4Checksum.read(file, true, (count, size) -> {
                    // The inspection pass also reports (0, 0). A changed expanded
                    // size cannot turn a fixed total into a misleading percentage.
                    if ((size != 0 && size != archive.expandedBytes) || count > archive.expandedBytes) {
                        throw new Pk4Checksum.Invalid(Pk4Checksum.Problem.CHANGED_FILE, name);
                    }
                    readBytes[0] = count;
                    progress(observer, Phase.VERIFYING, file.getName(), previousCount, planned.size(),
                             previousBytes + count, allBytes);
                    return true;
                });
                if (!archive.unchanged() || full.checksum != archive.checksum || full.expandedBytes != archive.expandedBytes) {
                    throw new Pk4Checksum.Invalid(Pk4Checksum.Problem.CHANGED_FILE, name);
                }
                Expected known = catalogue.get(name);
                if (known != null && known.checksum != 0 && full.checksum != known.checksum) {
                    // A modified archive of the selected layout fails the engine's startup check.
                    issues.add(new Issue(Code.CHECKSUM_MISMATCH, file.getName(),
                        known.required || selected.contains(name), known.checksum, full.checksum));
                } else if (known == null) {
                    issues.add(new Issue(Code.UNRECOGNIZED_ARCHIVE, file.getName(), false));
                }
                verified.add(archive);
            } catch (InterruptedIOException cancelled) {
                throw cancelled;
            } catch (IOException error) {
                issues.add(failed(file.getName(), error));
            }
            done += readBytes[0];
            ++finished;
        }
        // Do not return ready if an earlier file or directory changed while a
        // later archive was being read. This is a snapshot, never a lasting cache.
        List<Issue> finalIssues = new ArrayList<>();
        if (!directory.getCanonicalFile().equals(root) ||
                !inventory(root, finalIssues).equals(files) || !finalIssues.isEmpty()) {
            issues.add(new Issue(Code.CHANGED_FILE, root.getName(), true));
        }
        for (Archive archive : verified) {
            if (!archive.unchanged()) issues.add(new Issue(Code.CHANGED_FILE, archive.file.getName(), true));
        }
        progress(observer, Phase.VERIFYING, "", finished, planned.size(), done, total);
        return new Report(verified, issues);
    }
}
