// Los iconos del producto. Dibujados a mano y no traidos de una libreria: son
// once, pesan menos que el `import` que los buscaria, y asi todos comparten el
// mismo grosor de trazo y la misma caja.
//
// Sin "use client": los usan tanto paginas de servidor como componentes de
// cliente, y no tienen ningun estado.
//
// `currentColor` en todos a proposito: el icono se pinta del color del texto
// que lo rodea, asi que nunca hay que pasarle un color -y nunca se puede
// escribir uno a mano-.

type Props = {
  /** El tamanio, en unidades de Tailwind. Por defecto 16 px. */
  className?: string;
};

function Trazo({ children, className = "size-4" }: Props & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      // Decorativo: quien lo usa pone el texto o el aria-label que corresponda.
      aria-hidden="true"
      className={`shrink-0 ${className}`}
    >
      {children}
    </svg>
  );
}

export function IconoBuscar(p: Props) {
  return (
    <Trazo {...p}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </Trazo>
  );
}

export function IconoCerrar(p: Props) {
  return (
    <Trazo {...p}>
      <path d="M18 6 6 18M6 6l12 12" />
    </Trazo>
  );
}

export function IconoFlechaIzquierda(p: Props) {
  return (
    <Trazo {...p}>
      <path d="M19 12H5M12 19l-7-7 7-7" />
    </Trazo>
  );
}

export function IconoSistema(p: Props) {
  return (
    <Trazo {...p}>
      <rect x="2" y="4" width="20" height="13" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </Trazo>
  );
}

export function IconoSol(p: Props) {
  return (
    <Trazo {...p}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </Trazo>
  );
}

export function IconoLuna(p: Props) {
  return (
    <Trazo {...p}>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
    </Trazo>
  );
}

export function IconoEnviar(p: Props) {
  return (
    <Trazo {...p}>
      <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7Z" />
    </Trazo>
  );
}

export function IconoPausa(p: Props) {
  return (
    <Trazo {...p}>
      <rect x="6" y="4" width="4" height="16" rx="1" />
      <rect x="14" y="4" width="4" height="16" rx="1" />
    </Trazo>
  );
}

export function IconoReanudar(p: Props) {
  return (
    <Trazo {...p}>
      <path d="M6 4.5v15l13-7.5-13-7.5Z" />
    </Trazo>
  );
}

export function IconoMas(p: Props) {
  return (
    <Trazo {...p}>
      <path d="M12 5v14M5 12h14" />
    </Trazo>
  );
}

export function IconoCopiar(p: Props) {
  return (
    <Trazo {...p}>
      <rect x="9" y="9" width="12" height="12" rx="2" />
      <path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1" />
    </Trazo>
  );
}

export function IconoCheck(p: Props) {
  return (
    <Trazo {...p}>
      <path d="m20 6-11 11-5-5" />
    </Trazo>
  );
}
