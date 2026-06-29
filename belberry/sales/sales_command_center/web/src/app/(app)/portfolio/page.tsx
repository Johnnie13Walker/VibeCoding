import { notFound } from 'next/navigation';
import { getPortfolio } from '@/lib/portfolio';
import { getSession } from '@/lib/session';
import { canSeePortfolio } from '@/lib/portfolio-access';
import { PortfolioView } from '@/components/portfolio/PortfolioView';

export const dynamic = 'force-dynamic';

export default async function PortfolioPage() {
  const session = await getSession();
  if (!canSeePortfolio(session.email, session.role, session.bitrixId)) notFound();

  let data;
  try {
    data = await getPortfolio();
  } catch (e) {
    return (
      <div className="bb-page bb-fade">
        <div className="bb-hero" style={{ background: 'linear-gradient(135deg, #1f6a4f, #2b2a5e)', color: '#fff' }}>
          <h1 className="bb-hero-title">Портфолио</h1>
          <div className="bb-hero-sub">Витрина кейсов из Google Sheet</div>
        </div>
        <div className="bb-card" style={{ marginTop: 16 }}>
          <p style={{ color: 'var(--bb-red)', fontWeight: 600 }}>Не удалось загрузить портфолио из Google Sheet.</p>
          <p style={{ color: 'var(--bb-muted)', fontSize: 13, marginTop: 6 }}>
            Проверьте доступ сервис-аккаунта и переменную PORTFOLIO_SA_JSON/GOOGLE_SA_JSON. {String((e as Error).message).slice(0, 160)}
          </p>
        </div>
      </div>
    );
  }
  return <PortfolioView data={data} />;
}
