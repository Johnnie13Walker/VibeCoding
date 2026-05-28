import type { Metadata, Viewport } from "next";
import { Inter, Manrope } from "next/font/google";
import "./globals.css";
import { company, contacts } from "@/lib/content";

const inter = Inter({
  subsets: ["latin", "cyrillic"],
  display: "swap",
  variable: "--font-inter",
});

const manrope = Manrope({
  subsets: ["latin", "cyrillic"],
  display: "swap",
  variable: "--font-manrope",
  weight: ["500", "600", "700", "800"],
});

const description =
  "Digital-агентство Acoola Team: разработка, SEO, контекст, ORM и поддержка. 70+ проектов в работе ежемесячно. NPS 100 по независимой оценке 1С-Битрикс.";

export const metadata: Metadata = {
  metadataBase: new URL(company.url),
  title: {
    default: `${company.name} — Сайт как актив. Digital как процесс.`,
    template: `%s · ${company.name}`,
  },
  description,
  applicationName: company.name,
  keywords: [
    "digital-агентство",
    "разработка сайта",
    "SEO",
    "контекстная реклама",
    "управление репутацией",
    "Битрикс",
    "Acoola",
  ],
  authors: [{ name: company.legalName }],
  creator: company.legalName,
  openGraph: {
    type: "website",
    locale: "ru_RU",
    url: company.url,
    siteName: company.name,
    title: `${company.name} — Сайт как актив. Digital как процесс.`,
    description,
    images: [
      {
        url: "/og-image.jpg", // TODO: положить файл 1200×630 в /public
        width: 1200,
        height: 630,
        alt: `${company.name} — digital-агентство полного цикла`,
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: `${company.name} — Сайт как актив. Digital как процесс.`,
    description,
    images: ["/og-image.jpg"],
  },
  robots: {
    index: true,
    follow: true,
  },
};

export const viewport: Viewport = {
  themeColor: "#0a0a0b",
  width: "device-width",
  initialScale: 1,
};

const organizationJsonLd = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: company.legalName,
  alternateName: company.name,
  url: company.url,
  slogan: company.slogan,
  description,
  email: contacts.email,
  telephone: contacts.phone,
  address: {
    "@type": "PostalAddress",
    addressLocality: contacts.city,
    streetAddress: contacts.address,
    addressCountry: "RU",
  },
  // TODO: добавить sameAs со ссылками на соцсети агентства
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" className={`${inter.variable} ${manrope.variable}`}>
      <body>
        {children}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationJsonLd) }}
        />
        {/* TODO: METRIKA_ID — вставить идентификатор счётчика Яндекс.Метрики */}
        {/*
        <Script id="ym" strategy="afterInteractive">{`
          (function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
          m[i].l=1*new Date();k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
          (window, document,"script","https://mc.yandex.ru/metrika/tag.js","ym");
          ym(METRIKA_ID, "init", { clickmap:true, trackLinks:true, accurateTrackBounce:true, webvisor:true });
        `}</Script>
        */}
      </body>
    </html>
  );
}
