// Port: mudou um, muda o outro, com um teste de cada lado.
// helpers.js nao tem teste do lado web; estes casos descrevem o que o NewEntrySheet.jsx usa.
package br.financas.app.rules

import br.financas.app.data.AccountDto
import br.financas.app.data.CategoryDto
import br.financas.app.rules.EntryOptions.buildCategoryOptions
import br.financas.app.rules.EntryOptions.categoryIdForName
import br.financas.app.rules.EntryOptions.categoryLabel
import br.financas.app.rules.EntryOptions.categoryNameOf
import br.financas.app.rules.EntryOptions.filterCategoryOptions
import br.financas.app.rules.EntryOptions.pickDefaultAccountId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class EntryOptionsTest {
    private val categories = listOf(
        CategoryDto(id = "c1", name = "Alimentação", kind = "EXPENSE"),
        CategoryDto(id = "c2", name = "Outros", kind = "EXPENSE", parentId = "c1", parentName = "Alimentação"),
        CategoryDto(id = "c3", name = "Outros", kind = "BOTH"),
        CategoryDto(id = "c4", name = "Salário", kind = "INCOME"),
        CategoryDto(id = "c5", name = "Outros", kind = "EXPENSE", parentId = "c6", parentName = "Lazer"),
    )
    private val options = buildCategoryOptions(categories)

    @Test
    fun aSubcategoryReadsParentThenName() {
        assertEquals("Alimentação > Outros", categoryLabel(categories[1]))
        assertEquals("Alimentação", categoryLabel(categories[0]))
        assertEquals("Alimentação", categoryLabel(CategoryDto(id = "x", name = "Alimentação", parentName = "")))
    }

    @Test
    fun optionsKeepTheServerOrderAndTheId() {
        assertEquals(listOf("c1", "c2", "c3", "c4", "c5"), options.map { it.id })
        assertEquals("Lazer > Outros", options[4].label)
        assertEquals("Outros", options[4].name)
        assertEquals("c6", options[4].parentId)
        assertNull(options[0].parentId)
    }

    @Test
    fun expenseAndIncomeSeeTheirKindsAndBoth() {
        assertEquals(listOf("c1", "c2", "c3", "c5"), filterCategoryOptions(options, "EXPENSE").map { it.id })
        assertEquals(listOf("c3", "c4"), filterCategoryOptions(options, "INCOME").map { it.id })
        // O cartao e a transferencia leem como despesa.
        assertEquals(listOf("c1", "c2", "c3", "c5"), filterCategoryOptions(options, null).map { it.id })
    }

    @Test
    fun aBareNamePrefersTheRootThenTheFirst() {
        assertEquals("c3", categoryIdForName(options, "Outros"))
        assertEquals("c2", categoryIdForName(options.filter { it.id != "c3" }, "Outros"))
        assertEquals("c4", categoryIdForName(options, "Salário"))
        assertEquals("", categoryIdForName(options, "Investimento"))
        assertEquals("", categoryIdForName(options, ""))
        assertEquals("", categoryIdForName(options, null))
    }

    @Test
    fun theNameTravelsBesideTheId() {
        assertEquals("Outros", categoryNameOf(options, "c2"))
        assertEquals("", categoryNameOf(options, ""))
        assertEquals("", categoryNameOf(options, "nao-existe"))
    }

    @Test
    fun theDefaultAccountIsTheMarkedOneElseTheFirst() {
        val itau = AccountDto(id = "a1", name = "Itaú")
        val btg = AccountDto(id = "a2", name = "BTG", isDefault = true)
        assertEquals("a2", pickDefaultAccountId(listOf(itau, btg)))
        assertEquals("a1", pickDefaultAccountId(listOf(itau)))
        assertEquals("", pickDefaultAccountId(emptyList()))
    }
}
