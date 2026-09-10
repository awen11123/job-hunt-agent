from pydantic import BaseModel, ConfigDict, Field


class _ApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ProposeActionRequest(_ApiRequest):
    text: str = Field(min_length=1)


class ConfirmActionRequest(_ApiRequest):
    confirmation_token: str = Field(min_length=1)
