// Port: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/pages/lancamentos/helpers.js (buildCategoryOptions, categoryLabel,
// categoryIdForName, categoryNameOf, filterCategoryOptions, pickDefaultAccountId). Do lado web
// essas funcoes nao tem teste proprio; aqui: EntryOptionsTest.kt.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.data.AccountDto
import br.financas.app.data.CategoryDto

/** Uma opcao do seletor de categoria: o valor e o id, o rotulo "Pai > Nome" numa subcategoria. */
data class CategoryOption(
    val id: String,
    val name: String,
    val label: String,
    /** INCOME, EXPENSE ou BOTH. */
    val kind: String,
    val parentId: String?,
)

object EntryOptions {

    /** "Pai > Nome" numa subcategoria; so o nome na raiz. */
    @JvmStatic
    fun categoryLabel(category: CategoryDto): String =
        if (!category.parentName.isNullOrEmpty()) "${category.parentName} > ${category.name}" else category.name

    /** As opcoes na ordem do servidor (nome do pai, depois os filhos). */
    @JvmStatic
    fun buildCategoryOptions(categories: List<CategoryDto>): List<CategoryOption> =
        categories.map { category ->
            CategoryOption(
                id = category.id,
                name = category.name,
                label = categoryLabel(category),
                kind = category.kind,
                parentId = category.parentId?.takeIf { it.isNotEmpty() },
            )
        }

    /**
     * O id de uma categoria pelo nome (itens da fila de antes do id): a raiz primeiro, senao a
     * primeira com o nome. "" quando nao ha nome ou nenhuma bate.
     */
    @JvmStatic
    fun categoryIdForName(options: List<CategoryOption>, name: String?): String {
        if (name.isNullOrEmpty()) return ""
        val matches = options.filter { it.name == name }
        return (matches.firstOrNull { it.parentId == null } ?: matches.firstOrNull())?.id ?: ""
    }

    /** O nome (nao o rotulo) da categoria escolhida; "" sem escolha. */
    @JvmStatic
    fun categoryNameOf(options: List<CategoryOption>, id: String?): String =
        options.firstOrNull { it.id == id }?.name ?: ""

    /** Receita: tudo que nao e so despesa; qualquer outro tipo: tudo que nao e so receita. */
    @JvmStatic
    fun filterCategoryOptions(options: List<CategoryOption>, type: String?): List<CategoryOption> =
        if (type == "INCOME") options.filter { it.kind != "EXPENSE" } else options.filter { it.kind != "INCOME" }

    /** A conta padrao (is_default), senao a primeira; "" sem contas. */
    @JvmStatic
    fun pickDefaultAccountId(accounts: List<AccountDto>): String =
        (accounts.firstOrNull { it.isDefault } ?: accounts.firstOrNull())?.id ?: ""
}
