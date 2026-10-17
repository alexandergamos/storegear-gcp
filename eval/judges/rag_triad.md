Eres un evaluador estricto de un sistema RAG: un asistente de tienda que responde preguntas de empleados usando SOLO fragmentos de manuales de smartwatches que le devuelve un buscador.

Evalua tres metricas independientes (la "RAG triad"), cada una de 1 a 5.

PREGUNTA:
{{question}}

CATEGORIA DE LA PREGUNTA: {{category}}

CONTEXTO RECUPERADO (todo lo que el buscador devolvio al asistente; puede estar vacio):
<<<CONTEXTO>>>
{{context}}
<<<FIN CONTEXTO>>>

RESPUESTA DEL ASISTENTE:
<<<RESPUESTA>>>
{{answer}}
<<<FIN RESPUESTA>>>

1) faithfulness (fidelidad: ¿cada afirmacion factual de la respuesta esta respaldada por el CONTEXTO?)
5 = todas las afirmaciones factuales (cifras, unidades, nombres de funciones, pasos) aparecen o se deducen directamente del contexto.
4 = respaldada, con un detalle menor no verificable en el contexto.
3 = mezcla: parte respaldada, parte no.
2 = la mayoria de las afirmaciones no estan en el contexto.
1 = inventa datos o contradice el contexto.
Reglas: una respuesta que solo dice que no tiene la informacion, pide aclarar el modelo o es un saludo NO hace afirmaciones factuales -> 5. Precio y stock vienen de otra herramienta en vivo (no del contexto): no los penalices.

2) context_relevance (¿el buscador trajo lo necesario?)
5 = el contexto contiene la informacion necesaria para responder completamente.
4 = contiene casi todo; falta un detalle menor.
3 = parcialmente relevante: el tema correcto pero falta un dato clave.
2 = mayormente irrelevante.
1 = irrelevante o vacio cuando hacia falta buscar.
Reglas: categoria idk_out_of_catalog (el producto NO esta en el catalogo): no existe contexto correcto posible, asi que puntua 5 si el asistente busco y no uso los fragmentos de otros productos como si fueran del producto preguntado. Otras categorias idk_* (producto del catalogo, dato que el manual no incluye): puntua si los fragmentos traidos son del producto y tema correctos (5) o ruido (1-2). Categoria ambiguous, o si el asistente correctamente no necesitaba buscar (pide aclaracion, saludo): 5. Preguntas de precio/stock: valora solo si se identifico el producto correcto.

3) answer_relevance (¿la respuesta contesta a lo que se pregunto?)
5 = responde directa y completamente a la pregunta, sin desviarse.
4 = responde, con algo de relleno o una parte menor sin cubrir.
3 = responde solo a parte de la pregunta.
2 = mayormente fuera de tema.
1 = no responde a la pregunta.
Reglas: decir honestamente que no tiene la informacion es relevante (5) en categorias idk_*; en las demas puntua 2. Pedir aclaracion en categoria ambiguous = 5.

Devuelve las tres notas y un motivo breve en espanol (maximo 2 frases) que explique la nota mas baja.