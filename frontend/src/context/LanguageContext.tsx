import React, { createContext, useContext, useEffect, useState } from "react";
import { storage } from "@/src/utils/storage";
import { strings, Lang, StringKey } from "@/src/i18n";

type LangState = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (k: StringKey) => string;
};

const LangContext = createContext<LangState>({} as LangState);
export const useLang = () => useContext(LangContext);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("it");

  useEffect(() => {
    (async () => {
      const saved = (await storage.getItem("jobby_lang")) as Lang | null;
      if (saved === "it" || saved === "en") setLangState(saved);
    })();
  }, []);

  const setLang = (l: Lang) => {
    setLangState(l);
    storage.setItem("jobby_lang", l);
  };

  const t = (k: StringKey) => strings[lang][k] || strings.en[k] || k;

  return <LangContext.Provider value={{ lang, setLang, t }}>{children}</LangContext.Provider>;
}
