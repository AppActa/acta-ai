from pydantic import BaseModel, Field


class SkillDefinition(BaseModel):
    nome: str = Field(min_length=1, max_length=64)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)
    objetivo: str = Field(min_length=3, max_length=1000)
    regras: str = Field(min_length=3, max_length=3000)
    markdown: str = Field(min_length=1, max_length=5000)

