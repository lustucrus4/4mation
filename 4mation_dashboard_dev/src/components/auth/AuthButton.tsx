import { useEffect, useRef } from "react";
import { mountLab211Button } from "../../lib/lab211";

/** Hôte du bouton SSO Lab211 (Connexion / nom du compte). */
export default function AuthButton() {
  const slotRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (slotRef.current) {
      void mountLab211Button(slotRef.current);
    }
  }, []);

  return <div ref={slotRef} className="lab211-slot text-sm" aria-label="Compte Lab211" />;
}
