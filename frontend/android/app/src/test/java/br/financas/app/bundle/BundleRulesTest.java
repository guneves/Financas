package br.financas.app.bundle;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.function.Predicate;

import org.junit.Test;

/** As regras da tela baixada do servidor (BundleRules). */
public class BundleRulesTest {

    private static final String BUILTIN = "aaaaaaaaaaaaaaaa";
    private static final String V1 = "1111111111111111";
    private static final String V2 = "2222222222222222";
    private static final String BASE = "https://servidor.exemplo";

    private static BundleRules.State state(String current, boolean confirmed, String staged) {
        BundleRules.State state = new BundleRules.State();
        state.current = current;
        state.confirmed = confirmed;
        state.staged = staged;
        return state;
    }

    private static String decide(String target, BundleRules.State state) {
        return BundleRules.decide(target, 1, BASE, 1, BASE, BUILTIN, state);
    }

    private static Predicate<String> present(String... versions) {
        Set<String> set = new HashSet<>(Arrays.asList(versions));
        return set::contains;
    }

    @Test
    public void theServerVersionIsTheTarget() {
        assertEquals(BundleRules.UP_TO_DATE, decide(BUILTIN, state("", true, "")));
        assertEquals(BundleRules.DOWNLOAD, decide(V1, state("", true, "")));
        assertEquals(BundleRules.UP_TO_DATE, decide(V1, state(V1, true, "")));
        assertEquals(BundleRules.ALREADY_STAGED, decide(V2, state(V1, true, V2)));
        assertEquals(BundleRules.DOWNLOAD, decide(V2, state(V1, true, "")));
    }

    @Test
    public void aServerBackOnTheApkScreenGoesBackToIt() {
        assertEquals(BundleRules.USE_BUILTIN, decide(BUILTIN, state(V1, true, "")));
        assertEquals(BundleRules.ALREADY_STAGED, decide(BUILTIN, state(V1, true, BundleRules.BUILTIN)));
    }

    @Test
    public void aStagedScreenTheServerNoLongerServesIsDropped() {
        assertEquals(BundleRules.DROP_STAGED, decide(V1, state(V1, true, V2)));
        assertEquals(BundleRules.DROP_STAGED, decide(BUILTIN, state("", true, V2)));
    }

    @Test
    public void anotherNativeLevelIsNeverDownloaded() {
        assertEquals(BundleRules.INCOMPATIBLE, BundleRules.decide(V1, 2, BASE, 1, BASE, BUILTIN, state("", true, "")));
        // A volta para a tela do APK nao depende do nivel: ela e do proprio APK.
        assertEquals(BundleRules.USE_BUILTIN, BundleRules.decide(BUILTIN, 2, BASE, 1, BASE, BUILTIN, state(V1, true, "")));
    }

    @Test
    public void aScreenForAnotherServerIsRefused() {
        assertEquals(BundleRules.OTHER_SERVER,
            BundleRules.decide(V1, 1, "https://outro.exemplo", 1, BASE, BUILTIN, state("", true, "")));
        assertEquals(BundleRules.DOWNLOAD,
            BundleRules.decide(V1, 1, BASE + "/", 1, BASE, BUILTIN, state("", true, "")));
    }

    @Test
    public void aFailedScreenIsNotDownloadedAgain() {
        BundleRules.State state = state("", true, "");
        state.fail(V1);
        assertEquals(BundleRules.FAILED_BEFORE, decide(V1, state));
        assertEquals(BundleRules.DOWNLOAD, decide(V2, state));
    }

    @Test
    public void anApkWithoutAStampedScreenStillUpdates() {
        assertEquals(BundleRules.DOWNLOAD, BundleRules.decide(V1, 1, BASE, 1, BASE, "", state("", true, "")));
    }

    @Test
    public void aStagedScreenOpensInTrial() {
        BundleRules.State state = BundleRules.planLaunch(state("", true, V1), present(V1));
        assertEquals(V1, state.current);
        assertEquals("", state.staged);
        assertTrue(state.inTrial());
        assertEquals(1, state.attempts);
    }

    @Test
    public void aTrialThatNeverConfirmsFallsBackAfterTwoLaunches() {
        BundleRules.State state = BundleRules.planLaunch(state("", true, V1), present(V1));
        BundleRules.planLaunch(state, present(V1));
        assertEquals(V1, state.current);
        assertEquals(2, state.attempts);

        BundleRules.planLaunch(state, present(V1));
        assertEquals("", state.current);
        assertFalse(state.inTrial());
        assertTrue(state.failed.contains(V1));
    }

    @Test
    public void aConfirmedScreenKeepsOpening() {
        BundleRules.State state = BundleRules.planLaunch(state(V1, true, ""), present(V1));
        assertEquals(V1, state.current);
        assertFalse(state.inTrial());
        assertEquals(0, state.attempts);
    }

    @Test
    public void aMissingFolderOpensTheApkScreen() {
        BundleRules.State state = BundleRules.planLaunch(state(V1, true, ""), present());
        assertEquals("", state.current);

        state = BundleRules.planLaunch(state(V1, true, V2), present(V1));
        assertEquals("Staged incompleto: fica a atual", V1, state.current);
        assertEquals("", state.staged);
    }

    @Test
    public void stagingTheBuiltinGoesBackToTheApk() {
        BundleRules.State state = BundleRules.planLaunch(state(V1, true, BundleRules.BUILTIN), present(V1));
        assertEquals("", state.current);
        assertEquals("", state.staged);
        assertFalse(state.inTrial());
    }

    @Test
    public void theFailedListIsBounded() {
        BundleRules.State state = new BundleRules.State();
        for (int i = 0; i < BundleRules.MAX_FAILED + 5; i++) state.fail(String.format("%016x", i));
        assertEquals(BundleRules.MAX_FAILED, state.failed.size());
        assertTrue(state.failed.contains(String.format("%016x", BundleRules.MAX_FAILED + 4)));
        assertFalse(state.failed.contains(String.format("%016x", 0)));
    }

    @Test
    public void versionsAreTheManifestHash() {
        assertTrue(BundleRules.isValidVersion(V1));
        assertFalse(BundleRules.isValidVersion("../../etc"));
        assertFalse(BundleRules.isValidVersion(BundleRules.BUILTIN));
        assertFalse(BundleRules.isValidVersion(null));
    }

    @Test
    public void zipEntriesStayInsideTheFolder() {
        assertTrue(BundleRules.isSafeEntryName("index.html"));
        assertTrue(BundleRules.isSafeEntryName("assets/index-abc.js"));
        assertTrue(BundleRules.isSafeEntryName("fonts/"));
        assertFalse(BundleRules.isSafeEntryName("../x"));
        assertFalse(BundleRules.isSafeEntryName("assets/../../x"));
        assertFalse(BundleRules.isSafeEntryName("/etc/passwd"));
        assertFalse(BundleRules.isSafeEntryName("C:/x"));
        assertFalse(BundleRules.isSafeEntryName("a\\b"));
        assertFalse(BundleRules.isSafeEntryName(""));
    }
}
