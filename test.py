import os
import re
from pathlib import Path
from dotenv import load_dotenv
import mysql.connector
from flask import Flask, request, jsonify
from flask_cors import CORS

# Carrega o .env da mesma pasta do ficheiro
load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

app = Flask(__name__)

CORS(app, resources={
    r"/inscricoes": {"origins": "*"},
    r"/lista": {"origins": "*"}
})

db_config = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
}

def get_db_connection():
    return mysql.connector.connect(**db_config)


# -----------------------------
# Exceções e validação
# -----------------------------
class ValidationError(Exception):
    """Erro de validação do input do utilizador."""
    pass


def _require_str(data: dict, key: str, *, min_len=1, max_len=200) -> str:
    if key not in data:
        raise ValidationError(f"Campo em falta: {key}")

    value = data[key]
    if not isinstance(value, str):
        raise ValidationError(f"Campo '{key}' tem de ser texto (string).")

    value = value.strip()
    if len(value) < min_len:
        raise ValidationError(f"Campo '{key}' é demasiado curto.")
    if len(value) > max_len:
        raise ValidationError(f"Campo '{key}' é demasiado longo (máx {max_len}).")

    return value


def _require_int(data: dict, key: str, *, min_value=None, max_value=None) -> int:
    if key not in data:
        raise ValidationError(f"Campo em falta: {key}")

    value = data[key]

    # aceita int ou string numérica
    if isinstance(value, bool):
        raise ValidationError(f"Campo '{key}' inválido.")
    if isinstance(value, int):
        ivalue = value
    elif isinstance(value, str) and value.strip().isdigit():
        ivalue = int(value.strip())
    else:
        raise ValidationError(f"Campo '{key}' tem de ser número inteiro.")

    if min_value is not None and ivalue < min_value:
        raise ValidationError(f"Campo '{key}' tem de ser >= {min_value}.")
    if max_value is not None and ivalue > max_value:
        raise ValidationError(f"Campo '{key}' tem de ser <= {max_value}.")

    return ivalue


def _validate_email(email: str) -> str:
    # simples e suficiente para APIs básicas
    if len(email) > 150:
        raise ValidationError("Email demasiado longo (máx 150).")

    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    if not re.match(pattern, email):
        raise ValidationError("Email inválido.")
    return email


def _validate_contacto(contacto: str) -> str:
    # aceita números, espaços e + (ex: +351 912 345 678)
    cleaned = contacto.replace(" ", "")
    if not re.fullmatch(r"\+?\d{6,20}", cleaned):
        raise ValidationError("Contacto inválido. Use apenas dígitos e opcional '+'.")
    return contacto


# -----------------------------
# Classe com campos privados
# -----------------------------
class Inscricao:
    def __init__(self, nome: str, email: str, curso: str):
        self.__nome = nome
        self.__email = email
        self.__curso = curso

    @staticmethod
    def from_request(data: dict) -> "Inscricao":
        nome = _require_str(data, "nome", min_len=2, max_len=120)

        email = _require_str(data, "email", min_len=5, max_len=150)
        email = _validate_email(email)

        curso = _require_str(data, "curso", min_len=2, max_len=120)

        return Inscricao(nome, email, curso)

    def as_db_tuple(self):
        return (self.__nome, self.__email, self.__curso)

    def as_public_dict(self, inserted_id=None):
        payload = {
            "nome": self.__nome,
            "email": self.__email,
            "curso": self.__curso,
        }
        if inserted_id is not None:
            payload["id"] = inserted_id
        return payload
    


# -----------------------------
# Rotas
# -----------------------------
@app.route("/inscricoes", methods=["POST", "OPTIONS"])
def inserir_inscricao():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"erro": "JSON inválido ou vazio"}), 400

    try:
        inscricao = Inscricao.from_request(data)

        sql = """
        INSERT INTO inscricoes (nome, email, curso)
        VALUES (%s, %s, %s)
        """


        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, inscricao.as_db_tuple())
                conn.commit()
                new_id = cursor.lastrowid
        finally:
            conn.close()

        return jsonify({
            "mensagem": "Inscrição inserida com sucesso",
            "data": inscricao.as_public_dict(inserted_id=new_id)
        }), 201

    except ValidationError as ve:
        return jsonify({"erro": str(ve)}), 400

    except mysql.connector.Error as err:
        # não expor detalhes internos demais em produção; aqui fica simples
        return jsonify({"erro": "Erro de base de dados", "detalhe": str(err)}), 500

    except Exception:
        # fallback para erros inesperados
        return jsonify({"erro": "Erro interno"}), 500


@app.route("/lista", methods=["GET"])
def listar_inscricoes():
    try:
        sql = """
        SELECT nome, email, curso
        FROM inscricoes
        ORDER BY id DESC
        """

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql)
            rows = cursor.fetchall()
        finally:
            conn.close()

        return jsonify({
            "total": len(rows),
            "data": rows
        }), 200

    except mysql.connector.Error as err:
        return jsonify({
            "erro": "Erro de base de dados",
            "detalhe": str(err)
        }), 500

    except Exception:
        return jsonify({"erro": "Erro interno"}), 500



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
