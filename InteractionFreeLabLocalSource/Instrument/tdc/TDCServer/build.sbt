name := "TDCServer"
version := "1.0.12"
scalaVersion := "2.13.3"
organization := "com.interactionfree.instrument"
libraryDependencies += "com.interactionfree" %% "interactionfreescala" % "1.0.1"
libraryDependencies += "com.interactionfree.instrument" %% "universaltdc" % "1.2.0"
libraryDependencies += "org.scalatest" %% "scalatest" % "3.2.0" % "test"
//libraryDependencies += "org.scala-lang.modules" %% "scala-parser-combinators" % "1.1.2"
//val circeVersion = "0.12.3"
//libraryDependencies ++= Seq(
//  "io.circe" %% "circe-core",
//  "io.circe" %% "circe-generic",
//  "io.circe" %% "circe-parser"
//).map(_ % circeVersion)
//libraryDependencies += "org.json4s" %% "json4s-core" % "3.7.0-M4"
//libraryDependencies += "org.json4s" %% "json4s-jackson" % "3.7.0-M4"
scalacOptions ++= Seq("-feature")
scalacOptions ++= Seq("-deprecation")
