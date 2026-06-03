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
      setError(response.status === 429 ? 'Слишком много попыток. Попробуйте позже.' : 'Код не подошёл или уже истёк.');
      return;
    }

    router.replace(redirectTo);
    router.refresh();
  }

  return (
    <section className="w-full max-w-sm rounded-lg border border-[#e8e4f2] bg-white p-6 shadow-sm">
      <div className="mb-6 flex flex-col items-center text-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/belberry-logo.svg" alt="Belberry" className="h-9 w-auto" />
        <p className="mt-4 text-xs font-semibold uppercase tracking-wider text-[#5b50d6]">Командный центр продаж</p>
        <h1 className="mt-1 text-2xl font-extrabold text-[#1a1f3a]">Вход по Bitrix24</h1>
      </div>

      {step === 'email' ? (
        <form className="grid gap-4" onSubmit={requestCode}>
          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Email
            <input
              className="rounded-md border border-slate-300 px-3 py-2 outline-none focus:border-[#5b50d6]"
              autoComplete="email"
              inputMode="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <button
            className="rounded-lg bg-[#5b50d6] px-4 py-2 font-semibold text-white transition hover:bg-[#4a3fc5] disabled:cursor-not-allowed disabled:bg-[#b8b2ea]"
            disabled={loading}
          >
            Получить код
          </button>
        </form>
      ) : (
        <form className="grid gap-4" onSubmit={verify}>
          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Код из Bitrix24
            <input
              className="rounded-md border border-slate-300 px-3 py-2 tracking-widest outline-none focus:border-[#5b50d6]"
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
            className="rounded-lg bg-[#5b50d6] px-4 py-2 font-semibold text-white transition hover:bg-[#4a3fc5] disabled:cursor-not-allowed disabled:bg-[#b8b2ea]"
            disabled={loading}
          >
            Войти
          </button>
          <button
            className="text-sm font-medium text-slate-600 hover:text-slate-950"
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
