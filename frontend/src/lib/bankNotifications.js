// "Avisos dos bancos" (Fase 2, docs/notifications-pluggy-design.md §4): o
// interruptor bank_notifications de GET /api/inbox/settings. Ligado por padrao;
// um servidor antigo que nao manda o campo vale ligado, como o APK
// (InboxSettingsDto.bankNotifications = true).

export const BANK_NOTIFICATIONS_HINT = 'Itaú, BB e BTG gravam na hora pelo aviso do celular; a Pluggy confere depois.'

export function bankNotificationsOn(settings) {
  const value = settings?.bank_notifications
  return value === undefined || value === null ? true : value === true
}

export function bankNotificationsToast(on) {
  return on ? 'Os avisos dos bancos gravam na hora.' : 'Só o Flash grava pelo aviso; os bancos vêm pela Pluggy.'
}
