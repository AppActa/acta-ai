"""
db_scripts/init_mongo.py

Script de inicialização do MongoDB para o ACTA AI.

Uso:
    py -m db_scripts.init_mongo

Função:
- Testa conexão com MongoDB
- Cria índices necessários para memória conversacional
- Prepara collections principais usadas pelo chatbot
"""

from db_scripts.mongo import (
    MONGODB_DB_NAME,
    MONGODB_SESSIONS_COLLECTION,
    agora,
    criar_cliente_mongo,
    criar_indices_chat_sessoes,
)


def criar_collections_base(db):
    """
    Cria collections base do ACTA caso ainda não existam.

    O MongoDB cria collections automaticamente no primeiro insert,
    então aqui inserimos e removemos um documento temporário apenas
    para garantir que elas apareçam no banco.
    """

    collections = [
        MONGODB_SESSIONS_COLLECTION,
        "formularios_respostas",
        "ishikawa_analises",
        "cinco_porques",
        "licoes_aprendidas",
        "logs_ciclo",
    ]

    for nome in collections:
        if nome not in db.list_collection_names():
            db[nome].insert_one(
                {
                    "_temp": True,
                    "criado_em": agora(),
                    "descricao": "Documento temporário para criação da collection.",
                }
            )

            db[nome].delete_one({"_temp": True})

            print(f"Collection criada: {nome}")
        else:
            print(f"Collection já existe: {nome}")


def main():
    print("Conectando ao MongoDB...")

    client = criar_cliente_mongo()

    client.admin.command("ping")

    print("Conexão com MongoDB realizada com sucesso.")

    db = client[MONGODB_DB_NAME]

    print(f"Banco selecionado: {MONGODB_DB_NAME}")

    criar_collections_base(db)
    criar_indices_chat_sessoes(db[MONGODB_SESSIONS_COLLECTION])
    print(f"Índices criados/verificados: {MONGODB_SESSIONS_COLLECTION}")

    print("\nMongoDB inicializado com sucesso para o ACTA AI.")


if __name__ == "__main__":
    main()
