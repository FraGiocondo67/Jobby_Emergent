import React, { createContext, useContext, useEffect, useState } from "react";
import * as Localization from "expo-localization";
import { storage } from "@/src/utils/storage";
import { strings, Lang, StringKey } from "@/src/i18n";

type LangState = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (k: StringKey) => string;
};

const LangContext = createContext<LangState>({} as LangState);
export const useLang = () => useContext(LangContext);

// Default language from the device locale: Italian only if the device is Italian,
// otherwise English (per product decision).
function deviceLang(): Lang {
  try {
    const code = Localization.getLocales?.()?.[0]?.languageCode?.toLowerCase();
    return code === "it" ? "it" : "en";
  } catch {
    return "en";
  }
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(deviceLang());

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

  const t = (k: StringKey) => {
    const dict = (strings as any)?.[lang] || (strings as any)?.en || {};
    return dict?.[k] ?? (strings as any)?.en?.[k] ?? k;
  };

  return <LangContext.Provider value={{ lang, setLang, t }}>{children}</LangContext.Provider>;
}
