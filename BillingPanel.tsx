import React, { useEffect, useState } from 'react';
import { Coins, History, Shield, UserCheck, Users } from 'lucide-react';
import { apiClient } from '../../api/client';
import { useTranslation } from '../../i18n/LanguageContext';
import { BillingTariffsResponse, TokenTransactionItem, UserProfile } from '../../types/schema';

interface BillingPanelProps {
  currentUser: UserProfile | null;
  onUserUpdated: (user: UserProfile) => void;
  onOpenAuth: () => void;
}

export const BillingPanel: React.FC<BillingPanelProps> = ({ currentUser, onUserUpdated, onOpenAuth }) => {
  const { lang } = useTranslation();
  const [tariffs, setTariffs] = useState<BillingTariffsResponse | null>(null);
  const [transactions, setTransactions] = useState<TokenTransactionItem[]>([]);
  const [adminUsers, setAdminUsers] = useState<UserProfile[]>([]);
  const [statusMsg, setStatusMsg] = useState('');

  const [fullName, setFullName] = useState(currentUser?.full_name || '');
  const [newEmail, setNewEmail] = useState(currentUser?.email || '');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');

  const [targetUserId, setTargetUserId] = useState<number>(0);
  const [deltaTokens, setDeltaTokens] = useState<number>(100);
  const [targetRole, setTargetRole] = useState<'user' | 'admin'>('user');

  const loadData = async () => {
    try {
      const tData = await apiClient.getBillingTariffs();
      setTariffs(tData);
      if (currentUser) {
        const txData = await apiClient.getBillingTransactions(30);
        setTransactions(txData.items);
        if (currentUser.role === 'admin') {
          const uData = await apiClient.adminListUsers();
          setAdminUsers(uData.users);
          if (uData.users.length > 0 && !targetUserId) {
            const first = uData.users[0];
            setTargetUserId(first.id);
            setTargetRole(first.role);
          }
        }
      }
    } catch {
      /* локальный фоллбэк */
    }
  };

  useEffect(() => {
    setFullName(currentUser?.full_name || '');
    setNewEmail(currentUser?.email || '');
    loadData();
  }, [currentUser?.id, currentUser?.role]);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatusMsg('');
    try {
      const res = await apiClient.updateMyProfile({
        current_password: currentPassword,
        new_email: newEmail,
        full_name: fullName,
        new_password: newPassword || undefined,
      });
      onUserUpdated(res.user);
      setCurrentPassword('');
      setNewPassword('');
      setStatusMsg(lang === 'ru' ? 'Профиль и e-mail успешно обновлены.' : 'Profile updated successfully.');
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : 'Ошибка обновления');
    }
  };

  const handleAdminAdjust = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetUserId) return;
    setStatusMsg('');
    try {
      const res = await apiClient.adminAdjustUser({
        target_user_id: targetUserId,
        delta_tokens: Number(deltaTokens),
        new_role: targetRole,
        reason: 'Корректировка через кабинет администратора',
      });
      if (currentUser && res.user.id === currentUser.id) {
        onUserUpdated(res.user);
      }
      await loadData();
      setStatusMsg(lang === 'ru' ? `Аккаунт #${res.user.id} (${res.user.email}) обновлён.` : `User #${res.user.id} updated.`);
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : 'Ошибка администрирования');
    }
  };
  if (!currentUser) {
    return (
      <div className="max-w-3xl mx-auto bg-white rounded-2xl border border-slate-200 p-8 text-center space-y-4">
        <Coins className="w-12 h-12 text-amber-500 mx-auto" />
        <h2 className="text-xl font-bold text-slate-900">
          {lang === 'ru' ? 'Личный кабинет и кошелёк токенов' : 'Account & Token Wallet'}
        </h2>
        <p className="text-sm text-slate-600">
          {lang === 'ru'
            ? 'Вы работаете в гостевом режиме. Зарегистрируйтесь по e-mail, чтобы получить 100 бесплатных тестовых токенов, изолированное хранилище магазинов и историю операций.'
            : 'You are in guest mode. Register with your e-mail to receive 100 free trial tokens and isolated store workspace.'}
        </p>
        <button
          onClick={onOpenAuth}
          className="px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm cursor-pointer"
        >
          {lang === 'ru' ? 'Войти или зарегистрироваться (+100 токенов)' : 'Sign In / Register (+100 tokens)'}
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900">{currentUser.full_name || currentUser.email}</h1>
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${currentUser.role === 'admin' ? 'bg-purple-100 text-purple-800' : 'bg-slate-100 text-slate-700'}`}>
              {currentUser.role === 'admin' ? 'ADMIN' : 'USER'}
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-0.5">{currentUser.email}</p>
        </div>

        <div className="bg-amber-50 border border-amber-200 px-5 py-3 rounded-xl text-right">
          <div className="text-xs font-medium text-amber-800">
            {currentUser.role === 'admin' ? 'Режим тестирования (Admin)' : 'Доступный баланс'}
          </div>
          <div className="text-2xl font-extrabold text-amber-600">
            {currentUser.role === 'admin'
              ? `∞ (${currentUser.admin_spent_today} / ${currentUser.admin_daily_safety_limit ?? 5000} сегодня)`
              : `${currentUser.token_balance} токенов`}
          </div>
        </div>
      </div>

      {statusMsg && <div className="p-3 rounded-xl bg-blue-50 border border-blue-200 text-sm text-blue-900">{statusMsg}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white p-5 rounded-2xl border border-slate-200 space-y-3">
          <h3 className="font-semibold text-slate-900 flex items-center gap-2">
            <Coins className="w-4 h-4 text-amber-500" />
            {lang === 'ru' ? 'Тарифы ИИ-операций' : 'Operation Tariffs'}
          </h3>
          <div className="divide-y divide-slate-100 text-sm">
            {tariffs &&
              Object.entries(tariffs.operations).map(([key, op]) => (
                <div key={key} className="py-2 flex items-center justify-between">
                  <span className="text-slate-700">{lang === 'ru' ? op.title_ru : op.title_en}</span>
                  <span className="font-mono font-semibold text-slate-900">{op.cost} ток.</span>
                </div>
              ))}
          </div>
        </div>

        <form onSubmit={handleSaveProfile} className="bg-white p-5 rounded-2xl border border-slate-200 space-y-3">
          <h3 className="font-semibold text-slate-900 flex items-center gap-2">
            <UserCheck className="w-4 h-4 text-blue-600" />
            {lang === 'ru' ? 'Настройки профиля и смена E-mail' : 'Profile & E-mail Settings'}
          </h3>
          <input
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Имя"
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
          />
          <input
            type="email"
            required
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            placeholder="E-mail"
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
          />
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder={lang === 'ru' ? 'Новый пароль (необязательно)' : 'New password (optional)'}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
          />
          <input
            type="password"
            required
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            placeholder={lang === 'ru' ? 'Текущий пароль для подтверждения *' : 'Current password to confirm *'}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
          />
          <button type="submit" className="px-4 py-2 rounded-lg bg-slate-900 text-white text-sm font-medium cursor-pointer">
            {lang === 'ru' ? 'Сохранить изменения' : 'Save Profile'}
          </button>
        </form>
      </div>

      {currentUser.role === 'admin' && (
        <form onSubmit={handleAdminAdjust} className="bg-purple-50/70 p-5 rounded-2xl border border-purple-200 space-y-3">
          <h3 className="font-semibold text-purple-950 flex items-center gap-2">
            <Shield className="w-4 h-4 text-purple-700" />
            <Users className="w-4 h-4 text-purple-700" />
            {lang === 'ru' ? 'Панель администратора: управление пользователями и токенами' : 'Admin Panel: Users & Tokens'}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <select
              value={targetUserId}
              onChange={(e) => {
                const uid = Number(e.target.value);
                setTargetUserId(uid);
                const found = adminUsers.find((u) => u.id === uid);
                if (found) setTargetRole(found.role);
              }}
              className="px-3 py-2 bg-white border border-purple-200 rounded-lg text-sm"
            >
              {adminUsers.map((u) => (
                <option key={u.id} value={u.id}>
                  #{u.id} {u.email} ({u.role}, {u.token_balance} т.)
                </option>
              ))}
            </select>
            <input
              type="number"
              value={deltaTokens}
              onChange={(e) => setDeltaTokens(Number(e.target.value))}
              placeholder="+/- токенов"
              className="px-3 py-2 bg-white border border-purple-200 rounded-lg text-sm"
            />
            <select
              value={targetRole}
              onChange={(e) => setTargetRole(e.target.value as 'user' | 'admin')}
              className="px-3 py-2 bg-white border border-purple-200 rounded-lg text-sm"
            >
              <option value="user">Роль: user</option>
              <option value="admin">Роль: admin</option>
            </select>
            <button type="submit" className="px-4 py-2 rounded-lg bg-purple-700 hover:bg-purple-800 text-white text-sm font-semibold cursor-pointer">
              {lang === 'ru' ? 'Применить' : 'Apply'}
            </button>
          </div>
        </form>
      )}

      <div className="bg-white p-5 rounded-2xl border border-slate-200 space-y-3">
        <h3 className="font-semibold text-slate-900 flex items-center gap-2">
          <History className="w-4 h-4 text-slate-600" />
          {lang === 'ru' ? 'История операций с токенами' : 'Token Transaction History'}
        </h3>
        <div className="divide-y divide-slate-100 text-sm">
          {transactions.length === 0 && <p className="text-slate-400 py-2">Операций пока нет.</p>}
          {transactions.map((tx) => (
            <div key={tx.id} className="py-2 flex items-center justify-between gap-4">
              <div>
                <div className="font-medium text-slate-800">{tx.description}</div>
                <div className="text-xs text-slate-400">{tx.operation_type}</div>
              </div>
              <div className="text-right font-mono">
                <span className={tx.amount >= 0 ? 'text-emerald-600 font-bold' : 'text-rose-600 font-bold'}>
                  {tx.amount >= 0 ? `+${tx.amount}` : tx.amount}
                </span>
                <div className="text-xs text-slate-400">остаток: {tx.balance_after}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
