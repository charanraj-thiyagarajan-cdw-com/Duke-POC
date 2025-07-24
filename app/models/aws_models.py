from pydantic import BaseModel


class BoundingBox(BaseModel):
    """
    Represents the bounding box of a face, as returned by AWS Rekognition.
    """
    Width: float
    Height: float
    Left: float
    Top: float


class FaceInfo(BaseModel):
    """Represents the full face information object from Rekognition."""
    FaceId: str
    BoundingBox: BoundingBox
    ImageId: str
    Confidence: float