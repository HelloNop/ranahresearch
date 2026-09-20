from pydantic import BaseModel, ConfigDict


class OrmModel(BaseModel):
    """Read schema base: builds directly from ORM instances."""

    model_config = ConfigDict(from_attributes=True)
