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

// BLOCCO 9 (richiesta utente: aggiungere Cinese, Russo, Tedesco, Spagnolo,
// Francese): elenco centralizzato delle lingue supportate, usato sia per
// validare il valore salvato (sotto) sia dal selettore lingua in
// app/(tabs)/profile.tsx — un solo posto da aggiornare se in futuro se ne
// aggiungono altre.
export const SUPPORTED_LANGS: Lang[] = ["it", "en", "zh", "ru", "de", "es", "fr"];

// Lingua di default dal locale del device: prima solo it/en (default a
// inglese per chiunque altro); ora riconosce anche le 5 nuove lingue se il
// device è impostato in una di quelle, altrimenti inglese come prima.
function deviceLang(): Lang {
  try {
    const code = Localization.getLocales?.()?.[0]?.languageCode?.toLowerCase();
    return (SUPPORTED_LANGS as string[]).includes(code || "") ? (code as Lang) : "en";
  } catch {
    return "en";
  }
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(deviceLang());

  useEffect(() => {
    (async () => {
      const saved = (await storage.getItem("jobby_lang")) as Lang | null;
      if (saved && (SUPPORTED_LANGS as string[]).includes(saved)) setLangState(saved);
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
