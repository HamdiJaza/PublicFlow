# Source-review record

Review date: 18 October 2026. `rag/source_audit.json` records the scope and disposition
of every entry; `rag/sources.csv` controls inclusion in the index. Corpus text is a
manually authored summary, not an archived source page. Website content can change.

| Document | Direct source | Decision and scope |
|---|---|---|
| DOC-ROAD-01 | [Tunis citizen account](https://www.commune-tunis.gov.tn/page-de-login.aspx) | Enabled: account fields and complaint tracking; no verified pothole workflow or repair deadline. |
| DOC-ROAD-02 | [Tunis arrondissements](https://www.commune-tunis.gov.tn/arrondissements.aspx) | Enabled: directory; removed unsupported dispatch and brigade claims. |
| DOC-ROAD-03 | [MEHAT roads](https://www.mehat.gov.tn/fr/principaux-secteurs/ponts-et-chaussees/) | Enabled: road-administration scope; no citizen repair promise. |
| DOC-LIGHT-01 | [Tunis formalities](https://www.commune-tunis.gov.tn/demarches-formalite.aspx) | Enabled: public-lighting maintenance service; no invented hotline or booking steps. |
| DOC-LIGHT-02 | [STEG remote services](https://www.steg.com.tn/fr/centre-national-des-services-a-distance) | Enabled: listed emergency/general contacts; no dispatch guarantee. |
| DOC-WASTE-01 | Original municipal regulation PDF in source ledger | Excluded: 2009 document; current applicability not established. |
| DOC-WASTE-02 | [National waste-collection guide](https://www.collectiviteslocales.gov.tn/wp-content/uploads/2021/06/DMA_Guide-dOptimisation-de-la-Collecte-des-Dechets-Menagers-et-Assimiles-en-Tunisie.pdf) | Enabled as national guidance; not evidence of Tunis pickup bookings. |
| DOC-WATER-01 | [SONEDE contacts](https://www.sonede.com.tn/nous-contacter/) | Enabled: listed contact channels. |
| DOC-WATER-02 | [SONEDE FAQ](https://www.sonede.com.tn/espace-client/faq/) | Enabled: meter-reading diagnostic test; 30 minutes is not a repair deadline. |
| DOC-WATER-03 | Original ONAS reference in source ledger | Excluded: page/contact could not be revalidated. |
| DOC-TRANS-01 | [Tunis citizen account](https://www.commune-tunis.gov.tn/page-de-login.aspx) | Enabled: general account tracking only; replaces unverified help-desk claims. |
| DOC-LEGAL-01 | No primary text obtained | Excluded: no fabricated URL or assertion that a particular law is current. |

The two account summaries share a source and are not two independent authorities.
For new documents, record the precise supporting section and publication/update date
when known; do not substitute the retrieval date for an unknown publication date.
