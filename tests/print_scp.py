"""Impressora DICOM falsa (Print SCP) para os testes."""
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid
from pynetdicom import AE, evt
from pynetdicom.sop_class import (
    BasicColorPrintManagementMeta, BasicFilmBox, BasicFilmSession, BasicGrayscaleImageBox,
    BasicGrayscalePrintManagementMeta, Printer, Verification,
)


class FakePrinter:
    def __init__(self, port: int, ae_title: str = "FAKEPRN"):
        self.port, self.ae_title = port, ae_title
        self.sessions, self.film_boxes, self.images, self.printed = [], [], [], []
        ae = AE(ae_title=ae_title)
        for c in (BasicGrayscalePrintManagementMeta, BasicColorPrintManagementMeta, Verification):
            ae.add_supported_context(c)
        handlers = [(evt.EVT_N_CREATE, self.on_create), (evt.EVT_N_SET, self.on_set),
                    (evt.EVT_N_ACTION, self.on_action), (evt.EVT_N_DELETE, self.on_delete),
                    (evt.EVT_N_GET, self.on_get)]
        self.server = ae.start_server(("127.0.0.1", port), block=False, evt_handlers=handlers)

    def stop(self):
        self.server.shutdown()

    def on_create(self, event):
        req = event.request
        ds = event.attribute_list
        cls = req.AffectedSOPClassUID
        uid = req.AffectedSOPInstanceUID or generate_uid()
        if cls == BasicFilmSession:
            self.sessions.append(ds)
            return 0x0000, ds
        if cls == BasicFilmBox:
            self.film_boxes.append(ds)
            box = Dataset()
            box.ReferencedSOPClassUID = BasicGrayscaleImageBox
            box.ReferencedSOPInstanceUID = generate_uid()
            out = Dataset()
            out.update(ds)
            out.ReferencedImageBoxSequence = [box]
            return 0x0000, out
        return 0x0112, None

    def on_set(self, event):
        self.images.append(event.modification_list)
        return 0x0000, event.modification_list

    def on_action(self, event):
        self.printed.append(event.request.RequestedSOPInstanceUID)
        return 0x0000, None

    def on_delete(self, event):
        return 0x0000

    def on_get(self, event):
        ds = Dataset()
        ds.PrinterStatus = "NORMAL"
        ds.PrinterStatusInfo = "NORMAL"
        ds.PrinterName = "Falsa"
        return 0x0000, ds
