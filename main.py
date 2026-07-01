from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from urllib.parse import quote_plus, urlparse
from bs4 import BeautifulSoup
import requests
import re

app = FastAPI(title="CodazzIA API v1.5 - Consulta Oficial")

FUENTES_PERMITIDAS = {
    "consejo_estado": {
        "entidad": "Consejo de Estado",
        "dominio": "consejodeestado.gov.co",
        "busquedas": [
            "https://www.consejodeestado.gov.co/?s={query}"
        ],
        "jerarquia": 1
    },
    "corte_constitucional": {
        "entidad": "Corte Constitucional",
        "dominio": "corteconstitucional.gov.co",
        "busquedas": [
            "https://www.corteconstitucional.gov.co/relatoria/buscador_new/?search={query}",
            "https://www.corteconstitucional.gov.co/busqueda/?q={query}"
        ],
        "jerarquia": 2
    },
    "minhacienda": {
        "entidad": "Ministerio de Hacienda y Crédito Público",
        "dominio": "minhacienda.gov.co",
        "busquedas": [
            "https://www.minhacienda.gov.co/webcenter/portal/Minhacienda/search?query={query}",
            "https://www.minhacienda.gov.co/webcenter/portal/Minhacienda/pages_buscador?query={query}"
        ],
        "jerarquia": 3
    },
    "suin_juriscol": {
        "entidad": "SUIN-Juriscol",
        "dominio": "suin-juriscol.gov.co",
        "busquedas": [
            "https://www.suin-juriscol.gov.co/busqueda?search={query}",
            "https://www.suin-juriscol.gov.co/busqueda?texto={query}"
        ],
        "jerarquia": 4
    },
    "funcion_publica": {
        "entidad": "Función Pública",
        "dominio": "funcionpublica.gov.co",
        "busquedas": [
            "https://www.funcionpublica.gov.co/web/eva/resultados-busqueda?search={query}",
            "https://www.funcionpublica.gov.co/eva/gestornormativo/busqueda.php?termino={query}"
        ],
        "jerarquia": 5
    }
}


class ConsultaRequest(BaseModel):
    consulta: str
    fuentes: List[str]
    tipo_documento: str = "todos"
    fecha_desde: Optional[str] = None
    fecha_hasta: Optional[str] = None
    max_resultados: int = 5


def dominio_valido(url: str, dominio: str) -> bool:
    try:
        netloc = urlparse(url).netloc.lower()
        return dominio in netloc
    except Exception:
        return False


def limpiar_titulo(texto: str) -> str:
    texto = re.sub(r"\s+", " ", texto or "").strip()
    return texto[:250] if texto else "Resultado oficial"


def detectar_sentencia_corte(consulta: str):
    patron = r"(C|T|SU)[\-\s]?(\d{1,4})\s*(de)?\s*(\d{4})"
    match = re.search(patron, consulta, re.IGNORECASE)
    if not match:
        return None

    tipo = match.group(1).upper()
    numero = match.group(2)
    anio = match.group(4)

    numero_formateado = numero.zfill(3)
    url = f"https://www.corteconstitucional.gov.co/relatoria/{anio}/{tipo}-{numero_formateado}-{anio}.htm"

    return {
        "titulo": f"Sentencia {tipo}-{numero_formateado} de {anio}",
        "entidad": "Corte Constitucional",
        "fecha": f"{anio}-01-01",
        "tipo": "sentencia",
        "resumen": "Resultado construido mediante patrón oficial de relatoría de la Corte Constitucional.",
        "texto_relevante": "",
        "url_oficial": url,
        "dominio_validado": "corteconstitucional.gov.co",
        "fuente_verificada": True,
        "jerarquia": 2
    }


def buscar_en_fuente(consulta: str, fuente: str, max_resultados: int):
    config = FUENTES_PERMITIDAS[fuente]
    entidad = config["entidad"]
    dominio = config["dominio"]
    resultados = []
    query = quote_plus(consulta)

    headers = {
        "User-Agent": "Mozilla/5.0 CodazzIA/1.5"
    }

    if fuente == "corte_constitucional":
        sentencia = detectar_sentencia_corte(consulta)
        if sentencia:
            resultados.append(sentencia)

    for plantilla in config["busquedas"]:
        url_busqueda = plantilla.format(query=query)

        try:
            response = requests.get(url_busqueda, headers=headers, timeout=12)
            soup = BeautifulSoup(response.text, "html.parser")

            for a in soup.find_all("a", href=True):
                href = a.get("href")
                titulo = limpiar_titulo(a.get_text(" "))

                if href.startswith("/"):
                    href = f"https://www.{dominio}{href}"

                if href.startswith("http") and dominio_valido(href, dominio):
                    if len(titulo) < 8:
                        continue

                    resultados.append({
                        "titulo": titulo,
                        "entidad": entidad,
                        "fecha": None,
                        "tipo": "todos",
                        "resumen": "Resultado encontrado o enlazado desde buscador oficial autorizado.",
                        "texto_relevante": "",
                        "url_oficial": href,
                        "dominio_validado": dominio,
                        "fuente_verificada": True,
                        "jerarquia": config["jerarquia"]
                    })

                if len(resultados) >= max_resultados:
                    break

        except Exception:
            continue

        if len(resultados) >= max_resultados:
            break

    if not resultados:
        resultados.append({
            "titulo": f"Buscador oficial de {entidad}",
            "entidad": entidad,
            "fecha": None,
            "tipo": "busqueda_oficial",
            "resumen": "No se identificó un documento específico automáticamente. Se entrega enlace al buscador oficial para verificación manual.",
            "texto_relevante": "",
            "url_oficial": config["busquedas"][0].format(query=query),
            "dominio_validado": dominio,
            "fuente_verificada": True,
            "jerarquia": config["jerarquia"]
        })

    return resultados[:max_resultados]


@app.get("/")
def home():
    return {
        "estado": "API activa",
        "version": "1.5",
        "servicio": "CodazzIA - Consulta Oficial Normativa y Jurisprudencial",
        "fuentes_permitidas": list(FUENTES_PERMITIDAS.keys())
    }


@app.post("/consulta-oficial")
def consulta_oficial(request: ConsultaRequest):
    resultados = []

    for fuente in request.fuentes:
        if fuente not in FUENTES_PERMITIDAS:
            raise HTTPException(status_code=403, detail=f"Fuente no permitida: {fuente}")

        resultados.extend(
            buscar_en_fuente(
                consulta=request.consulta,
                fuente=fuente,
                max_resultados=request.max_resultados
            )
        )

    resultados = sorted(resultados, key=lambda x: x.get("jerarquia", 99))

    return {
        "consulta": request.consulta,
        "fuentes_consultadas": request.fuentes,
        "resultados": resultados[:request.max_resultados],
        "advertencia": "Respuesta generada como orientación jurídica. Verificar siempre la fuente oficial antes de adoptar decisiones institucionales."
    }
