"use client";

import { useTheme } from "@/components/hooks/useTheme";
import { useReveal } from "@/components/hooks/useReveal";
import { TopNav } from "@/components/landing/TopNav";
import { Hero } from "@/components/landing/Hero";
import { ThreeQuestions } from "@/components/landing/ThreeQuestions";
import { Surfaces } from "@/components/landing/Surfaces";
import { VerdictPath } from "@/components/landing/VerdictPath";
import { RealVerdict } from "@/components/landing/RealVerdict";
import { JudgmentLayer } from "@/components/landing/JudgmentLayer";
import { SplunkNative } from "@/components/landing/SplunkNative";
import { AuditEvidence } from "@/components/landing/AuditEvidence";
import { HonestByDefault } from "@/components/landing/HonestByDefault";
import { GetStarted } from "@/components/landing/GetStarted";
import { Footer } from "@/components/landing/Footer";

export default function LandingPage() {
  const { theme, toggle } = useTheme();
  useReveal();

  return (
    <div
      className={`ag page ${theme === "dark" ? "theme-dark" : "theme-paper"}`}
      data-material="splunk"
    >
      <TopNav theme={theme} onToggleTheme={toggle} />
      <Hero />
      <ThreeQuestions />
      <Surfaces />
      <VerdictPath />
      <RealVerdict />
      <JudgmentLayer />
      <SplunkNative />
      <AuditEvidence />
      <HonestByDefault />
      <GetStarted />
      <Footer />
    </div>
  );
}
