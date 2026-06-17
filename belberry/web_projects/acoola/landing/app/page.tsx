import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { Hero } from "@/components/sections/Hero";
import { Stats } from "@/components/sections/Stats";
import { Services } from "@/components/sections/Services";
import { Cases } from "@/components/sections/Cases";
import { Approach } from "@/components/sections/Approach";
import { Team } from "@/components/sections/Team";
import { Awards } from "@/components/sections/Awards";
import { Testimonials } from "@/components/sections/Testimonials";
import { FAQ } from "@/components/sections/FAQ";
import { CTA } from "@/components/sections/CTA";

export default function Page() {
  return (
    <>
      <Header />
      <main id="main">
        <Hero />
        <Stats />
        <Services />
        <Cases />
        <Approach />
        <Team />
        <Awards />
        <Testimonials />
        <FAQ />
        <CTA />
      </main>
      <Footer />
    </>
  );
}
