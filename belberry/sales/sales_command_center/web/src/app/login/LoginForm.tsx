'use client';

import { useRouter } from 'next/navigation';
import { FormEvent, useState } from 'react';

interface LoginFormProps {
  redirectTo: string;
}

type Step = 'email' | 'code';

export function LoginForm({ redirectTo }: LoginFormProps) {
  const router = useRouter();
  const [step, setStep] = useState<Step>('email');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function requestCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError('');

    const response = await fetch('/api/auth/request-code', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ email }),
    });

    setLoading(false);

    if (!response.ok) {
      setError(response.status === 429 ? 'Слишком много попыток. Попробуйте позже.' : 'Email не найден в Bitrix24.');
      return;
    }

    setStep('code');
  }

  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError('');

    const response = await fetch('/api/auth/verify', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ email, code }),
    });

    setLoading(false);

    if (!response.ok) {
      if (response.status === 429) {
        setError('Слишком много попыток. Попробуйте позже.');
      } else if (response.status === 403) {
        setError('Доступ закрыт: аккаунт не активен в Bitrix24.');
      } else if (response.status >= 500) {
        setError('Временный сбой сервиса. Код не потрачен — нажмите «Войти» ещё раз.');
      } else {
        setError('Код не подошёл или уже истёк.');
      }
      return;
    }

    router.replace(redirectTo);
    router.refresh();
  }

  return (
    <section className="w-full max-w-sm rounded-3xl border border-[#e8e8ed] bg-white p-8 shadow-[0_4px_24px_rgba(0,0,0,0.06)]">
      <div className="mb-7 flex flex-col items-center text-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/belberry-logo.svg" alt="Belberry" className="h-9 w-auto" />
        <p className="mt-5 text-xs font-medium uppercase tracking-wider text-[#6e6e73]">Командный центр продаж</p>
        <h1 className="mt-1.5 text-2xl font-semibold tracking-[-0.02em] text-[#1d1d1f]">Вход по Bitrix24</h1>
      </div>

      {step === 'email' ? (
        <form className="grid gap-4" onSubmit={requestCode}>
          <label className="grid gap-2 text-sm font-medium text-[#1d1d1f]">
            Email
            <input
              className="rounded-xl border border-[#d2d2d7] px-3.5 py-2.5 outline-none transition focus:border-[#5b50d6] focus:ring-2 focus:ring-[#5b50d6]/20"
              autoComplete="email"
              inputMode="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <button
            className="rounded-full bg-[#5b50d6] px-4 py-2.5 font-semibold text-white transition hover:bg-[#4a3fc5] disabled:cursor-not-allowed disabled:bg-[#b8b2ea]"
            disabled={loading}
          >
            Получить код
          </button>
        </form>
      ) : (
        <form className="grid gap-4" onSubmit={verify}>
          <label className="grid gap-2 text-sm font-medium text-[#1d1d1f]">
            Код из Bitrix24
            <input
              className="rounded-xl border border-[#d2d2d7] px-3.5 py-2.5 tracking-widest outline-none transition focus:border-[#5b50d6] focus:ring-2 focus:ring-[#5b50d6]/20"
              autoComplete="one-time-code"
              inputMode="numeric"
              pattern="\d{6}"
              maxLength={6}
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
              required
            />
          </label>
          <button
            className="rounded-full bg-[#5b50d6] px-4 py-2.5 font-semibold text-white transition hover:bg-[#4a3fc5] disabled:cursor-not-allowed disabled:bg-[#b8b2ea]"
            disabled={loading}
          >
            Войти
          </button>
          <button
            className="text-sm font-medium text-[#6e6e73] transition hover:text-[#1d1d1f]"
            type="button"
            onClick={() => setStep('email')}
          >
            Изменить email
          </button>
        </form>
      )}

      {error ? <p className="mt-4 text-sm font-medium text-red-700">{error}</p> : null}
    </section>
  );
}
