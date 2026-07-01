from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlparse

app = FastAPI(title="Consulta Oficial Normativa y Jurisprudencial CodazzIA")

FUENTES_PERMITIDAS = {
    "consejo_estado": {
        "entidad": "Consejo de Estado",
        "dominio": "consejodeestado.gov.co"
    },
    "corte_constitucional": {
        "entidad": "Corte Constitucional",
        "dominio": "corteconstitucional.gov.co"
    },
    "minhacienda": {
        "entidad": "Ministerio de Hacienda y Crédito Público",
        "dominio": "minhacienda.gov.co"
    },
    "suin_juriscol": {
        "entidad": "SUIN-Juriscol",
        "dominio": "suin-juriscol.gov.co"
    },
    "funcion_publica": {
        "entidad": "Función Pública",
        "dominio": "funcionpublica.gov.co"
    }
}

class ConsultaRequest(BaseModel):
    consulta: str
    fuentes: List[str]
    tipo_documento: str = "todos"
    fecha_desde: Optional[str] = None
    fecha_hasta: Optional[str] = None
    max_resultados: int = 5

@app.get("/")
def home():
    return {
        "estado": "API activa",
        "servicio": "CodazzIA - Consulta Oficial Normativa y Jurisprudencial",
        "fuentes_permitidas": list(FUENTES_PERMITIDAS.keys())
    }

@app.post("/consulta-oficial")
def consulta_oficial(request: ConsultaRequest):
    resultados = []

    for fuente in request.fuentes:
        if fuente not in FUENTES_PERMITIDAS:
            raise HTTPException(status_code=403, detail=f"Fuente no permitida: {fuente}")

        entidad = FUENTES_PERMITIDAS[fuente]["entidad"]
        dominio = FUENTES_PERMITIDAS[fuente]["dominio"]

        query = quote_plus(f"{request.consulta} site:{dominio}")
        url_busqueda = f"https://www.google.com/search?q={query}"

        headers = {"User-Agent": "Mozilla/5.0"}

        try:
            response = requests.get(url_busqueda, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")

            for link in soup.find_all("a"):
                href = link.get("href", "")

                if "/url?q=" in href:
                    url = href.split("/url?q=")[1].split("&")[0]
                    parsed = urlparse(url)

                    if dominio in parsed.netloc:
                        resultados.append({
                            "titulo": link.get_text(strip=True)[:250] or "Resultado oficial",
                            "entidad": entidad,
                            "fecha": None,
                            "tipo": request.tipo_documento,
                            "resumen": "Resultado encontrado en fuente oficial autorizada.",
                            "texto_relevante": "",
                            "url_oficial": url,
                            "dominio_validado": dominio,
                            "fuente_verificada": True,
                            "jerarquia": 1
                        })

                if len(resultados) >= request.max_resultados:
                    break

        except Exception as e:
            resultados.append({
                "titulo": "Error de consulta",
                "entidad": entidad,
                "fecha": None,
                "tipo": "otro",
                "resumen": f"No fue posible consultar la fuente: {str(e)}",
                "texto_relevante": "",
                "url_oficial": f"https://{dominio}",
                "dominio_validado": dominio,
                "fuente_verificada": False,
                "jerarquia": 99
            })

    return {
        "consulta": request.consulta,
        "fuentes_consultadas": request.fuentes,
        "resultados": resultados[:request.max_resultados],
        "advertencia": "Respuesta generada como orientación jurídica. Verificar siempre la fuente oficial antes de adoptar decisiones institucionales."
    }
