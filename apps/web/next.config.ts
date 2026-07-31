import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Empaqueta solo los archivos que el server necesita en runtime, en vez de
  // arrastrar todo node_modules a la imagen. Es lo que recomienda la doc de
  // Next para desplegar con Docker.
  output: "standalone",
};

export default nextConfig;
