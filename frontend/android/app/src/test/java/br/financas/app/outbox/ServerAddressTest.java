package br.financas.app.outbox;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

import org.junit.Test;

public class ServerAddressTest {

    private static final String NEW = "https://guilhermeserver.tail5084ff.ts.net:8443";

    @Test
    public void theOld443AddressMovesToTheNewDefault() {
        assertEquals(NEW, ServerAddress.migrate("https://guilhermeserver.tail5084ff.ts.net", NEW));
        assertEquals(NEW, ServerAddress.migrate("https://guilhermeserver.tail5084ff.ts.net/", NEW));
        assertEquals(NEW, ServerAddress.migrate("https://guilhermeserver.tail5084ff.ts.net:443", NEW));
    }

    @Test
    public void anyOtherAddressStays() {
        assertEquals(NEW, ServerAddress.migrate(NEW, NEW));
        assertEquals("https://outro.example", ServerAddress.migrate("https://outro.example", NEW));
        assertEquals("", ServerAddress.migrate("", NEW));
        assertNull(ServerAddress.migrate(null, NEW));
    }

    @Test
    public void aBuildStillPointingAtTheOldAddressChangesNothing() {
        String old = ServerAddress.OLD_BASE;
        assertEquals(old, ServerAddress.migrate(old, old));
        assertEquals(old, ServerAddress.migrate(old, ""));
    }
}
