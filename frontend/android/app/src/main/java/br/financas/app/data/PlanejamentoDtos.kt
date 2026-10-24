package br.financas.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Planejar (Orcamento, Recorrentes, Metas) e A receber: as respostas que as telas nativas leem.
// Dinheiro e percentual sao Money (BigDecimal do texto do JSON), nunca Double.

/** GET /api/monthly-plan?month= (build_monthly_plan(), services/monthly_plan.py). */
@Serializable
data class MonthlyPlanDto(
    val month: String = "",
    /** PAST, CURRENT ou FUTURE. */
    val period: String = "CURRENT",
    val plan: PlanRowDto? = null,
    val income: PlanIncomeDto? = null,
    /** Sem `invest`: uma copia de antes de 038, ignorada (a tela pede de novo). */
    val invest: PlanLevelDto? = null,
    val spend: PlanLevelDto? = null,
    val unallocated: PlanLevelDto? = null,
    val categories: PlanCategoriesDto? = null,
    @SerialName("plan_balance") val planBalance: Money? = null,
    @SerialName("daily_available") val dailyAvailable: Money? = null,
    val actual: PlanActualDto? = null,
    val progress: PlanProgressDto? = null,
    val flags: List<PlanFlagDto> = emptyList(),
)

@Serializable
data class PlanRowDto(
    val id: String = "",
    @SerialName("source_month") val sourceMonth: String? = null,
    val inherited: Flag = false,
    @SerialName("needs_income") val needsIncome: Flag = false,
    @SerialName("income_amount") val incomeAmount: Money? = null,
    @SerialName("invest_percent") val investPercent: Money? = null,
    @SerialName("spend_percent") val spendPercent: Money? = null,
    val legacy: PlanLegacyDto? = null,
)

@Serializable
data class PlanLegacyDto(
    @SerialName("invest_amount") val investAmount: Money? = null,
    @SerialName("spend_amount") val spendAmount: Money? = null,
)

@Serializable
data class PlanIncomeDto(val planned: Money? = null, val received: Money? = null)

@Serializable
data class PlanLevelDto(val percent: Money? = null, val amount: Money? = null)

@Serializable
data class PlanActualDto(val spent: Money? = null, val invested: Money? = null)

@Serializable
data class PlanProgressDto(
    @SerialName("spend_percent") val spendPercent: Money? = null,
    @SerialName("invest_percent") val investPercent: Money? = null,
    @SerialName("invest_remaining") val investRemaining: Money? = null,
)

/** Um alerta do plano: o codigo e os valores; o texto sai de rules/MonthlyPlan.kt (flagText). */
@Serializable
data class PlanFlagDto(
    val code: String = "",
    /** loss, warning, info ou gain. */
    val tone: String = "info",
    val amount: Money? = null,
    val over: Money? = null,
    val percent: Money? = null,
    @SerialName("days_left") val daysLeft: Int? = null,
    @SerialName("goal_id") val goalId: String? = null,
    @SerialName("goal_name") val goalName: String? = null,
    @SerialName("target_month") val targetMonth: String? = null,
    val missing: Money? = null,
)

@Serializable
data class PlanCategoriesDto(
    val items: List<PlanBudgetDto> = emptyList(),
    val totals: PlanBudgetTotalsDto? = null,
    val unassigned: PlanLevelDto? = null,
)

/** Uma categoria do mes (serialize_budget(), services/budgets.py). */
@Serializable
data class PlanBudgetDto(
    val id: String,
    @SerialName("category_id") val categoryId: String? = null,
    @SerialName("category_name") val categoryName: String? = null,
    @SerialName("parent_name") val parentName: String? = null,
    @SerialName("category_kind") val categoryKind: String? = null,
    @SerialName("planned_percent") val plannedPercent: Money? = null,
    @SerialName("planned_amount") val plannedAmount: Money? = null,
    @SerialName("legacy_amount") val legacyAmount: Money? = null,
    val rollover: Flag = false,
    val note: String? = null,
    val spent: Money? = null,
    val carryover: Money? = null,
    val available: Money? = null,
    val remaining: Money? = null,
    val percent: Money? = null,
    /** OK, WARNING, OVER ou NEEDS_INCOME. */
    val status: String = "OK",
    @SerialName("needs_income") val needsIncome: Flag = false,
)

@Serializable
data class PlanBudgetTotalsDto(
    @SerialName("assigned_percent") val assignedPercent: Money? = null,
    @SerialName("over_count") val overCount: Int = 0,
)

/** GET /api/budgets/<id>/lines?month=. */
@Serializable
data class BudgetLinesDto(val spent: Money? = null, val lines: List<BudgetLineDto> = emptyList())

@Serializable
data class BudgetLineDto(
    val id: String,
    /** TRANSACTION ou CARD. */
    val source: String = "TRANSACTION",
    val type: String? = null,
    val category: String? = null,
    val date: String? = null,
    val description: String? = null,
    /** A parte do dono. */
    val amount: Money? = null,
    @SerialName("total_amount") val totalAmount: Money? = null,
    val shared: Flag = false,
    @SerialName("account_name") val accountName: String? = null,
    @SerialName("card_name") val cardName: String? = null,
    val installments: Int? = null,
    val refund: Flag = false,
    val subcategory: Flag = false,
)

/** POST /api/budgets/copy: o que interessa a tela. */
@Serializable
data class BudgetCopyDto(val created: Int = 0, val updated: Int = 0, val skipped: Int = 0)

// ---- Recorrentes ----

/** GET /api/recurring. */
@Serializable
data class RecurringListDto(
    val items: List<RecurringDto> = emptyList(),
    @SerialName("pending_count") val pendingCount: Int = 0,
    val today: String? = null,
)

/** Uma recorrencia (serialize_recurring(), services/recurring.py). */
@Serializable
data class RecurringDto(
    val id: String,
    val description: String? = null,
    val amount: Money? = null,
    /** INCOME ou EXPENSE. */
    val type: String = "EXPENSE",
    val category: String? = null,
    @SerialName("category_id") val categoryId: String? = null,
    @SerialName("account_id") val accountId: String? = null,
    /** WEEKLY, MONTHLY ou YEARLY. */
    val frequency: String = "MONTHLY",
    @SerialName("interval_count") val intervalCount: Int? = 1,
    @SerialName("start_date") val startDate: String? = null,
    @SerialName("end_date") val endDate: String? = null,
    @SerialName("next_run_date") val nextRunDate: String? = null,
    val active: Flag = true,
    @SerialName("paused_at") val pausedAt: String? = null,
    /** ACTIVE, PAUSED ou FINISHED. */
    val status: String = "ACTIVE",
    @SerialName("pending_count") val pendingCount: Int = 0,
)

/** GET /api/recurring/forecast?days=90. */
@Serializable
data class RecurringForecastDto(
    val occurrences: List<RecurringOccurrenceDto> = emptyList(),
    val windows: Map<String, ForecastWindowDto> = emptyMap(),
)

@Serializable
data class RecurringOccurrenceDto(
    @SerialName("recurring_id") val recurringId: String? = null,
    val date: String? = null,
    val type: String = "EXPENSE",
    val amount: Money? = null,
    val category: String? = null,
    val description: String? = null,
    val pending: Flag = false,
)

@Serializable
data class ForecastWindowDto(val income: Money? = null, val expense: Money? = null, val net: Money? = null)

/** DELETE /api/recurring/<id>. */
@Serializable
data class RecurringDeletedDto(@SerialName("kept_transactions") val keptTransactions: Int = 0)

// ---- Metas ----

/** Uma meta de GET /api/goals (serialize_goal(), services/goals.py): tudo calculado na leitura. */
@Serializable
data class GoalDto(
    val id: String,
    val name: String = "",
    /** NET_WORTH, PORTFOLIO, ASSET_CLASS ou MONTHLY_INCOME. */
    val kind: String = "NET_WORTH",
    @SerialName("kind_label") val kindLabel: String? = null,
    @SerialName("asset_class") val assetClass: String? = null,
    @SerialName("target_amount") val targetAmount: Money? = null,
    @SerialName("monthly_contribution") val monthlyContribution: Money? = null,
    @SerialName("annual_return_percent") val annualReturnPercent: Money? = null,
    @SerialName("target_date") val targetDate: String? = null,
    @SerialName("target_month") val targetMonth: String? = null,
    val current: Money? = null,
    val remaining: Money? = null,
    val percent: Money? = null,
    val reached: Flag = false,
    @SerialName("estimated_months") val estimatedMonths: Int? = null,
    @SerialName("estimated_month") val estimatedMonth: String? = null,
    @SerialName("required_contribution") val requiredContribution: Money? = null,
    /** true, false ou null (sem data). */
    @SerialName("on_track") val onTrack: Boolean? = null,
    @SerialName("income_last_12_months") val incomeLast12Months: Money? = null,
)

// ---- A receber ----

/** Um item de GET /api/receivables (list_receivables(), services/sharing.py). */
@Serializable
data class ReceivableDto(
    /** TRANSACTION ou CARD_PURCHASE. */
    val kind: String = "TRANSACTION",
    val id: String,
    val date: String? = null,
    val description: String? = null,
    val category: String? = null,
    val amount: Money? = null,
    @SerialName("share_mode") val shareMode: String? = null,
    @SerialName("others_amount") val othersAmount: Money? = null,
    val person: String? = null,
    @SerialName("settled_at") val settledAt: String? = null,
    @SerialName("card_name") val cardName: String? = null,
)

// ---- Ajustes ----

/** PATCH /api/auth/me -> { user }. */
@Serializable
data class MeDto(val user: MeUserDto? = null)

@Serializable
data class MeUserDto(val id: String? = null, val email: String? = null, val username: String? = null)
